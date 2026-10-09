"""`FindingRepository` over the Fabric Warehouse: `tcc_ops.agent_finding_resolution`. [ADR-007]

The same append-only semantics as the SQLite adapter, which the shared contract
suite enforces: a decision closes the live one (`superseded_at`) and inserts
itself in ONE transaction, retried on a snapshot-isolation conflict; reopening
closes without inserting. Every statement is tenant-scoped through `tenant_sql`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
from infrastructure.persistence.sqlite_findings import FindingResolution
from infrastructure.persistence.tenant_sql import TenantScopedQuery, run_in_transaction
from infrastructure.persistence.warehouse_claims import from_db_instant, rows_as_dicts, to_db_instant

_COLUMNS = (
    "finding_id", "client_id", "tax_year", "resolution", "detail", "note",
    "decided_by", "decided_at", "superseded_at",
)


def _instant(value: str | None) -> datetime | None:
    return to_db_instant(datetime.fromisoformat(value)) if value else None


def _iso(value: Any) -> str | None:
    instant = from_db_instant(value)
    return instant.isoformat() if instant else None


def _row(row: dict[str, Any]) -> FindingResolution:
    return FindingResolution(
        finding_id=row["finding_id"],
        client_id=int(row["client_id"]),
        tax_year=int(row["tax_year"]),
        resolution=row["resolution"],
        detail=json.loads(row["detail"]) if row["detail"] else None,
        note=row["note"],
        decided_by=row["decided_by"],
        decided_at=_iso(row["decided_at"]),
        superseded_at=_iso(row["superseded_at"]),
    )


class WarehouseFindingRepository:
    """Durable finding resolutions in the Warehouse."""

    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def _read(self, client_id: int, sql: str, params: list[Any]) -> list[FindingResolution]:
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(cursor, sql, params)
                return [_row(r) for r in rows_as_dicts(cursor)]
            finally:
                cursor.close()

    def live(self, client_id: int, tax_year: int | None = None) -> list[FindingResolution]:
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM {OPS_SCHEMA}.agent_finding_resolution "
            "WHERE {tenant} AND superseded_at IS NULL"
        )
        params: list[Any] = []
        if tax_year is not None:
            sql += " AND tax_year = ?"
            params.append(tax_year)
        return self._read(client_id, sql + " ORDER BY decided_at, finding_id", params)

    def history(self, client_id: int, finding_id: str) -> list[FindingResolution]:
        return self._read(
            client_id,
            f"SELECT {', '.join(_COLUMNS)} FROM {OPS_SCHEMA}.agent_finding_resolution "
            "WHERE {tenant} AND finding_id = ? "
            "ORDER BY decided_at, CASE WHEN superseded_at IS NULL THEN 1 ELSE 0 END",
            [finding_id],
        )

    def record(self, resolution: FindingResolution) -> FindingResolution:
        """Append, closing whatever it supersedes — one transaction, retried on conflict."""
        scoped = TenantScopedQuery(resolution.client_id)

        def work(cursor: Any) -> None:
            scoped.execute(
                cursor,
                f"UPDATE {OPS_SCHEMA}.agent_finding_resolution SET superseded_at = ? "
                "WHERE {tenant} AND finding_id = ? AND superseded_at IS NULL",
                [_instant(resolution.decided_at), resolution.finding_id],
            )
            scoped.insert(
                cursor,
                f"{OPS_SCHEMA}.agent_finding_resolution",
                _COLUMNS,
                [[
                    resolution.finding_id,
                    resolution.client_id,
                    resolution.tax_year,
                    resolution.resolution,
                    json.dumps(resolution.detail) if resolution.detail else None,
                    resolution.note,
                    resolution.decided_by,
                    _instant(resolution.decided_at),
                    None,
                ]],
            )

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return resolution

    def reopen(self, client_id: int, finding_id: str, *, decided_by: str) -> None:
        """Withdraw the live decision. The prior one is closed, never deleted."""
        scoped = TenantScopedQuery(client_id)
        now = to_db_instant(datetime.now(timezone.utc))

        def work(cursor: Any) -> None:
            scoped.execute(
                cursor,
                f"UPDATE {OPS_SCHEMA}.agent_finding_resolution SET superseded_at = ? "
                "WHERE {tenant} AND finding_id = ? AND superseded_at IS NULL",
                [now, finding_id],
            )

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
