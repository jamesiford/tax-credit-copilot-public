"""`ClaimRepository` over the Fabric Warehouse: claims and engagements. [ADR-007]

The Warehouse is the only operational store (D1). This adapter keeps the
SQLite adapter's semantics exactly, and the shared contract suite in
`tests/contracts/` holds the two to that.

**Append-only, in one transaction.** A status change closes the live row
(`effective_to`) and inserts the new one. Both statements run in ONE explicit
transaction: split, there is a window with two live rows (a double-counted
claim) or none (a cell that vanishes mid-read).

**Conflicts are retried.** Fabric Warehouse runs writes under snapshot
isolation with table-level locking, so two concurrent writers to the same table
can abort one another with an update conflict. `run_in_transaction` retries the
whole close-then-insert with capped backoff; re-running it is safe because the
close re-reads whichever row is live at that moment.

**Every statement goes through `tenant_sql`.** The table has no partition key,
so the client predicate is what stands between one client's figures and
another's screen. The portfolio read is the single, logged exemption.

**`effective_from` / `effective_to` are DATE here** (DDL v2.0), where SQLite
keeps the full instant. Two changes to one cell on the same day therefore share
a date; history orders by date, then live-last, then `decided_at`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from domain.claims import (
    ClaimStatus,
    EngagementScope,
    ProgramClaim,
    ProgramEngagement,
    Provenance,
)
from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
from infrastructure.persistence.tenant_sql import (
    TenantScopedQuery,
    run_in_transaction,
    tenant_exempt,
)

_COLUMNS = (
    "claim_id", "client_id", "entity_id", "program_code", "tax_year", "status",
    "provenance", "identified_usd", "claimed_usd", "certified_usd",
    "average_headcount", "base_average_headcount", "threshold_jobs",
    "is_base_year",
    "identified_run_id", "assumption_set_id", "rule_pack_version", "filed_on",
    "filing_reference", "decided_by", "decided_at", "decline_reason",
    "effective_from", "effective_to",
)
_ENGAGEMENT_COLUMNS = ("client_id", "program_code", "scope", "effective_from", "effective_to", "note")

_PORTFOLIO = tenant_exempt("portfolio coverage spans clients by design")


# ------------------------------------------------------------- conversions


def to_db_instant(value: datetime | None) -> datetime | None:
    """Naive UTC for DATETIME2: pyodbc does not carry a zone."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def from_db_instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    raise TypeError(f"not an instant: {value!r}")


def to_db_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    return value


def from_db_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return value


def from_db_money(value: Any) -> Decimal:
    """DECIMAL(19,4) back to the shortest exact form: 31000.0000 -> 31000."""
    if value is None:
        return Decimal("0")
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if amount == amount.to_integral_value():
        return amount.quantize(Decimal(1))
    return amount.normalize()


def rows_as_dicts(cursor: Any) -> list[dict[str, Any]]:
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _row_to_claim(row: dict[str, Any]) -> ProgramClaim:
    return ProgramClaim(
        claim_id=str(row["claim_id"]),
        client_id=int(row["client_id"]),
        entity_id=int(row["entity_id"]) if row["entity_id"] is not None else None,
        program_code=row["program_code"],
        tax_year=int(row["tax_year"]),
        status=ClaimStatus(row["status"]),
        provenance=Provenance(row["provenance"]),
        identified_usd=from_db_money(row["identified_usd"]),
        claimed_usd=from_db_money(row["claimed_usd"]),
        certified_usd=from_db_money(row["certified_usd"]),
        average_headcount=row["average_headcount"],
        base_average_headcount=row["base_average_headcount"],
        threshold_jobs=row["threshold_jobs"],
        is_base_year=bool(row["is_base_year"]),
        identified_run_id=row["identified_run_id"],
        assumption_set_id=row["assumption_set_id"],
        rule_pack_version=row["rule_pack_version"],
        filed_on=from_db_date(row["filed_on"]),
        filing_reference=row["filing_reference"],
        decided_by=row["decided_by"],
        decided_at=from_db_instant(row["decided_at"]),
        decline_reason=row["decline_reason"],
        effective_from=from_db_instant(row["effective_from"]),
        effective_to=from_db_instant(row["effective_to"]),
    )


def _claim_values(claim: ProgramClaim) -> list[Any]:
    return [
        claim.claim_id,
        claim.client_id,
        claim.entity_id,
        claim.program_code,
        claim.tax_year,
        claim.status.value,
        claim.provenance.value,
        claim.identified_usd,
        claim.claimed_usd,
        claim.certified_usd,
        claim.average_headcount,
        claim.base_average_headcount,
        claim.threshold_jobs,
        bool(claim.is_base_year),
        claim.identified_run_id,
        claim.assumption_set_id,
        claim.rule_pack_version,
        claim.filed_on,
        claim.filing_reference,
        claim.decided_by,
        to_db_instant(claim.decided_at),
        claim.decline_reason,
        to_db_date(claim.effective_from),
        to_db_date(claim.effective_to),
    ]


def _in_list(values: list[Any]) -> str:
    return ", ".join("?" for _ in values)


class WarehouseClaimRepository:
    """`ClaimRepository` backed by `tcc_ops.program_claim` and `program_engagement`."""

    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    @property
    def connection(self) -> FabricWarehouseConnection:
        return self._connection

    def _read(self, client_id: int, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(cursor, sql, list(params))
                return rows_as_dicts(cursor)
            finally:
                cursor.close()

    # ----------------------------------------------------------- claim read

    def current(self, client_id: int, program_code: str, tax_year: int) -> ProgramClaim | None:
        rows = self._read(
            client_id,
            f"SELECT TOP 1 {', '.join(_COLUMNS)} FROM {OPS_SCHEMA}.program_claim "
            "WHERE {tenant} AND program_code = ? AND tax_year = ? AND effective_to IS NULL "
            "ORDER BY effective_from DESC, decided_at DESC",
            [program_code.upper(), tax_year],
        )
        return _row_to_claim(rows[0]) if rows else None

    def history(self, client_id: int, program_code: str, tax_year: int) -> list[ProgramClaim]:
        rows = self._read(
            client_id,
            f"SELECT {', '.join(_COLUMNS)} FROM {OPS_SCHEMA}.program_claim "
            "WHERE {tenant} AND program_code = ? AND tax_year = ? "
            "ORDER BY effective_from, CASE WHEN effective_to IS NULL THEN 1 ELSE 0 END, decided_at",
            [program_code.upper(), tax_year],
        )
        return [_row_to_claim(r) for r in rows]

    def coverage(
        self,
        client_id: int,
        *,
        program_codes: Iterable[str] | None = None,
        tax_years: Iterable[int] | None = None,
    ) -> list[ProgramClaim]:
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM {OPS_SCHEMA}.program_claim "
            "WHERE {tenant} AND effective_to IS NULL"
        )
        params: list[Any] = []
        codes = [c.upper() for c in program_codes] if program_codes is not None else None
        if codes is not None:
            if not codes:
                return []
            sql += f" AND program_code IN ({_in_list(codes)})"
            params.extend(codes)
        years = list(tax_years) if tax_years is not None else None
        if years is not None:
            if not years:
                return []
            sql += f" AND tax_year IN ({_in_list(years)})"
            params.extend(years)
        sql += " ORDER BY program_code, tax_year"
        return [_row_to_claim(r) for r in self._read(client_id, sql, params)]

    def portfolio_coverage(
        self,
        *,
        client_ids: Iterable[int] | None = None,
        tax_years: Iterable[int] | None = None,
    ) -> list[ProgramClaim]:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM {OPS_SCHEMA}.program_claim WHERE effective_to IS NULL"
        params: list[Any] = []
        ids = list(client_ids) if client_ids is not None else None
        if ids is not None:
            if not ids:
                return []
            sql += f" AND client_id IN ({_in_list(ids)})"
            params.extend(ids)
        years = list(tax_years) if tax_years is not None else None
        if years is not None:
            if not years:
                return []
            sql += f" AND tax_year IN ({_in_list(years)})"
            params.extend(years)
        sql += " ORDER BY client_id, program_code, tax_year"
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                _PORTFOLIO.execute(cursor, sql, params)
                return [_row_to_claim(r) for r in rows_as_dicts(cursor)]
            finally:
                cursor.close()

    # ---------------------------------------------------------- claim write

    def record(self, claim: ProgramClaim) -> ProgramClaim:
        """Append, closing whatever it supersedes — one transaction, retried on conflict."""
        scoped = TenantScopedQuery(claim.client_id)

        def work(cursor: Any) -> None:
            scoped.execute(
                cursor,
                f"UPDATE {OPS_SCHEMA}.program_claim SET effective_to = ? "
                "WHERE {tenant} AND program_code = ? AND tax_year = ? AND effective_to IS NULL",
                [to_db_date(claim.effective_from), claim.program_code, claim.tax_year],
            )
            scoped.insert(cursor, f"{OPS_SCHEMA}.program_claim", _COLUMNS, [_claim_values(claim)])

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return claim

    # ----------------------------------------------------------- engagement

    def engagements(self, client_id: int) -> list[ProgramEngagement]:
        rows = self._read(
            client_id,
            f"SELECT {', '.join(_ENGAGEMENT_COLUMNS)} FROM {OPS_SCHEMA}.program_engagement "
            "WHERE {tenant} AND effective_to IS NULL ORDER BY program_code",
        )
        return [
            ProgramEngagement(
                client_id=int(r["client_id"]),
                program_code=r["program_code"],
                scope=EngagementScope(r["scope"]),
                effective_from=from_db_instant(r["effective_from"]),
                effective_to=from_db_instant(r["effective_to"]),
                note=r["note"],
            )
            for r in rows
        ]

    def set_engagement(self, engagement: ProgramEngagement) -> ProgramEngagement:
        scoped = TenantScopedQuery(engagement.client_id)

        def work(cursor: Any) -> None:
            scoped.execute(
                cursor,
                f"UPDATE {OPS_SCHEMA}.program_engagement SET effective_to = ? "
                "WHERE {tenant} AND program_code = ? AND effective_to IS NULL",
                [to_db_date(engagement.effective_from), engagement.program_code],
            )
            scoped.insert(
                cursor,
                f"{OPS_SCHEMA}.program_engagement",
                _ENGAGEMENT_COLUMNS,
                [[
                    engagement.client_id,
                    engagement.program_code,
                    engagement.scope.value,
                    to_db_date(engagement.effective_from),
                    to_db_date(engagement.effective_to),
                    engagement.note,
                ]],
            )

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return engagement
