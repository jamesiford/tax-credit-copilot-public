"""SQLite adapter for the claim repository. [ADR-002]

The dev and CI implementation. Not a fallback and not technical debt: CI must
not need a Warehouse to run the suite, and the reference parity gate has to
stay a fast unit test rather than becoming an integration test.

`sqlite3` is imported here and nowhere else outside this package.

Two storage decisions are worth stating, because both would be easy to get
wrong and hard to notice:

**Money is TEXT, never REAL.** SQLite's REAL is a float, and a float cannot
hold 0.1. Every figure here lands on a filed tax return, so the values go in as
strings and come out as `Decimal`. A schema that stored them as REAL would work
perfectly in every test and be wrong by cents in production.

**History is append-only.** A status change inserts a new row and closes the
prior one by setting `effective_to`. Nothing is updated in place except that
closing stamp, because the question an audit asks is "what did you believe on
the day you filed?" and an overwritten row cannot answer it.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from domain.claims import (
    ClaimStatus,
    EngagementScope,
    ProgramClaim,
    ProgramEngagement,
    Provenance,
)

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "operational.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS program_claim (
    claim_id            TEXT PRIMARY KEY,
    client_id           INTEGER NOT NULL,
    entity_id           INTEGER,
    program_code        TEXT    NOT NULL,
    tax_year            INTEGER NOT NULL,
    status              TEXT    NOT NULL,
    provenance          TEXT    NOT NULL,
    -- TEXT, not REAL. See the module docstring: REAL is a float.
    identified_usd      TEXT    NOT NULL DEFAULT '0',
    claimed_usd         TEXT    NOT NULL DEFAULT '0',
    certified_usd       TEXT    NOT NULL DEFAULT '0',
    -- The jobs reasoning behind identified_usd. REAL is fine here: a headcount
    -- average is a measurement, not money, and nothing downstream sums it into
    -- a figure that reaches a return.
    average_headcount      REAL,
    base_average_headcount REAL,
    threshold_jobs         REAL,
    -- The earliest year held. Net-new needs a prior year, so this cell's
    -- identified figure is zero by construction and cannot be compared with a
    -- filed amount. See domain.claims.Outcome.BASE_YEAR.
    is_base_year        INTEGER NOT NULL DEFAULT 0,
    identified_run_id   TEXT,
    assumption_set_id   TEXT,
    rule_pack_version   TEXT,
    filed_on            TEXT,
    filing_reference    TEXT,
    decided_by          TEXT,
    decided_at          TEXT,
    decline_reason      TEXT,
    effective_from      TEXT    NOT NULL,
    effective_to        TEXT,
    -- Enforced in the database as well as the domain. A row that reached here
    -- through some future code path still cannot be a reasonless decline.
    CHECK (status <> 'declined' OR (decline_reason IS NOT NULL AND trim(decline_reason) <> ''))
);

-- Tenant leads every index because tenant leads every query.
CREATE INDEX IF NOT EXISTS ix_claim_cell
    ON program_claim (client_id, program_code, tax_year, effective_from);

CREATE INDEX IF NOT EXISTS ix_claim_live
    ON program_claim (client_id, tax_year) WHERE effective_to IS NULL;

-- One live record per cell. Without this a double-write would leave two
-- "current" rows and the coverage matrix would silently double-count a claim.
CREATE UNIQUE INDEX IF NOT EXISTS ux_claim_one_live_per_cell
    ON program_claim (client_id, program_code, tax_year) WHERE effective_to IS NULL;

CREATE TABLE IF NOT EXISTS program_engagement (
    client_id      INTEGER NOT NULL,
    program_code   TEXT    NOT NULL,
    scope          TEXT    NOT NULL,
    effective_from TEXT    NOT NULL,
    effective_to   TEXT,
    note           TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_engagement_one_live
    ON program_engagement (client_id, program_code) WHERE effective_to IS NULL;
"""

_COLUMNS = (
    "claim_id", "client_id", "entity_id", "program_code", "tax_year", "status",
    "provenance", "identified_usd", "claimed_usd", "certified_usd",
    "average_headcount", "base_average_headcount", "threshold_jobs",
    "is_base_year",
    "identified_run_id", "assumption_set_id", "rule_pack_version", "filed_on",
    "filing_reference", "decided_by", "decided_at", "decline_reason",
    "effective_from", "effective_to",
)

#: Columns added after the table shipped. `CREATE TABLE IF NOT EXISTS` leaves an
#: existing database untouched, so a new column has to be added explicitly.
_ADDED_COLUMNS = (
    ("is_base_year", "INTEGER NOT NULL DEFAULT 0"),
)


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_claim(row: sqlite3.Row) -> ProgramClaim:
    return ProgramClaim(
        claim_id=row["claim_id"],
        client_id=row["client_id"],
        entity_id=row["entity_id"],
        program_code=row["program_code"],
        tax_year=row["tax_year"],
        status=ClaimStatus(row["status"]),
        provenance=Provenance(row["provenance"]),
        identified_usd=Decimal(row["identified_usd"]),
        claimed_usd=Decimal(row["claimed_usd"]),
        certified_usd=Decimal(row["certified_usd"]),
        average_headcount=row["average_headcount"],
        base_average_headcount=row["base_average_headcount"],
        threshold_jobs=row["threshold_jobs"],
        is_base_year=bool(row["is_base_year"]),
        identified_run_id=row["identified_run_id"],
        assumption_set_id=row["assumption_set_id"],
        rule_pack_version=row["rule_pack_version"],
        filed_on=date.fromisoformat(row["filed_on"]) if row["filed_on"] else None,
        filing_reference=row["filing_reference"],
        decided_by=row["decided_by"],
        decided_at=_parse_dt(row["decided_at"]),
        decline_reason=row["decline_reason"],
        effective_from=_parse_dt(row["effective_from"]),
        effective_to=_parse_dt(row["effective_to"]),
    )


def _claim_to_params(claim: ProgramClaim) -> tuple[Any, ...]:
    return (
        claim.claim_id,
        claim.client_id,
        claim.entity_id,
        claim.program_code,
        claim.tax_year,
        claim.status.value,
        claim.provenance.value,
        str(claim.identified_usd),
        str(claim.claimed_usd),
        str(claim.certified_usd),
        claim.average_headcount,
        claim.base_average_headcount,
        claim.threshold_jobs,
        int(claim.is_base_year),
        claim.identified_run_id,
        claim.assumption_set_id,
        claim.rule_pack_version,
        claim.filed_on.isoformat() if claim.filed_on else None,
        claim.filing_reference,
        claim.decided_by,
        claim.decided_at.isoformat() if claim.decided_at else None,
        claim.decline_reason,
        claim.effective_from.isoformat(),
        claim.effective_to.isoformat() if claim.effective_to else None,
    )


def _placeholders(values: Iterable[Any]) -> str:
    return ", ".join("?" for _ in values)


class SqliteClaimRepository:
    """`ClaimRepository` over SQLite.

    Connections are per-thread: FastAPI runs sync handlers in a threadpool, and
    a shared connection would raise on the second worker to touch it.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path(os.getenv("OPERATIONAL_DB", _DEFAULT_PATH))
        self._local = threading.local()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ------------------------------------------------------------ plumbing

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._local.conn = conn
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        with conn:
            conn.executescript(_SCHEMA)
            existing = {r["name"] for r in conn.execute("PRAGMA table_info(program_claim)")}
            for column, declaration in _ADDED_COLUMNS:
                if column not in existing:
                    conn.execute(f"ALTER TABLE program_claim ADD COLUMN {column} {declaration}")

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ----------------------------------------------------------- claim read

    def current(self, client_id: int, program_code: str, tax_year: int) -> ProgramClaim | None:
        row = self._connect().execute(
            "SELECT * FROM program_claim "
            "WHERE client_id = ? AND program_code = ? AND tax_year = ? AND effective_to IS NULL",
            (client_id, program_code.upper(), tax_year),
        ).fetchone()
        return _row_to_claim(row) if row else None

    def history(self, client_id: int, program_code: str, tax_year: int) -> list[ProgramClaim]:
        rows = self._connect().execute(
            "SELECT * FROM program_claim "
            "WHERE client_id = ? AND program_code = ? AND tax_year = ? "
            "ORDER BY effective_from, rowid",
            (client_id, program_code.upper(), tax_year),
        ).fetchall()
        return [_row_to_claim(r) for r in rows]

    def coverage(
        self,
        client_id: int,
        *,
        program_codes: Iterable[str] | None = None,
        tax_years: Iterable[int] | None = None,
    ) -> list[ProgramClaim]:
        sql = "SELECT * FROM program_claim WHERE client_id = ? AND effective_to IS NULL"
        params: list[Any] = [client_id]

        codes = [c.upper() for c in program_codes] if program_codes is not None else None
        if codes is not None:
            if not codes:
                return []
            sql += f" AND program_code IN ({_placeholders(codes)})"
            params.extend(codes)

        years = list(tax_years) if tax_years is not None else None
        if years is not None:
            if not years:
                return []
            sql += f" AND tax_year IN ({_placeholders(years)})"
            params.extend(years)

        sql += " ORDER BY program_code, tax_year"
        return [_row_to_claim(r) for r in self._connect().execute(sql, params).fetchall()]

    def portfolio_coverage(
        self,
        *,
        client_ids: Iterable[int] | None = None,
        tax_years: Iterable[int] | None = None,
    ) -> list[ProgramClaim]:
        sql = "SELECT * FROM program_claim WHERE effective_to IS NULL"
        params: list[Any] = []

        ids = list(client_ids) if client_ids is not None else None
        if ids is not None:
            if not ids:
                return []
            sql += f" AND client_id IN ({_placeholders(ids)})"
            params.extend(ids)

        years = list(tax_years) if tax_years is not None else None
        if years is not None:
            if not years:
                return []
            sql += f" AND tax_year IN ({_placeholders(years)})"
            params.extend(years)

        sql += " ORDER BY client_id, program_code, tax_year"
        return [_row_to_claim(r) for r in self._connect().execute(sql, params).fetchall()]

    # ---------------------------------------------------------- claim write

    def record(self, claim: ProgramClaim) -> ProgramClaim:
        """Append, closing whatever it supersedes.

        Close-then-insert runs in ONE transaction. Splitting them would leave a
        window with either two live rows for a cell (double-counted claim) or
        none (a cell that vanishes mid-read).
        """
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE program_claim SET effective_to = ? "
                "WHERE client_id = ? AND program_code = ? AND tax_year = ? AND effective_to IS NULL",
                (
                    claim.effective_from.isoformat(),
                    claim.client_id,
                    claim.program_code,
                    claim.tax_year,
                ),
            )
            conn.execute(
                f"INSERT INTO program_claim ({', '.join(_COLUMNS)}) "
                f"VALUES ({_placeholders(_COLUMNS)})",
                _claim_to_params(claim),
            )
        return claim

    # ----------------------------------------------------------- engagement

    def engagements(self, client_id: int) -> list[ProgramEngagement]:
        rows = self._connect().execute(
            "SELECT * FROM program_engagement WHERE client_id = ? AND effective_to IS NULL "
            "ORDER BY program_code",
            (client_id,),
        ).fetchall()
        return [
            ProgramEngagement(
                client_id=r["client_id"],
                program_code=r["program_code"],
                scope=EngagementScope(r["scope"]),
                effective_from=_parse_dt(r["effective_from"]),
                effective_to=_parse_dt(r["effective_to"]),
                note=r["note"],
            )
            for r in rows
        ]

    def set_engagement(self, engagement: ProgramEngagement) -> ProgramEngagement:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE program_engagement SET effective_to = ? "
                "WHERE client_id = ? AND program_code = ? AND effective_to IS NULL",
                (
                    engagement.effective_from.isoformat(),
                    engagement.client_id,
                    engagement.program_code,
                ),
            )
            conn.execute(
                "INSERT INTO program_engagement "
                "(client_id, program_code, scope, effective_from, effective_to, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    engagement.client_id,
                    engagement.program_code,
                    engagement.scope.value,
                    engagement.effective_from.isoformat(),
                    engagement.effective_to.isoformat() if engagement.effective_to else None,
                    engagement.note,
                ),
            )
        return engagement
