"""Agent findings: what an agent noticed, and what a human decided about it.

The Agent Workbench listed registered agents and their status. That is topology
— it shows how the software is arranged, which is exactly what the editorial
test cuts. Nobody filing a tax return needs to know that `HeadcountAgent` is
registered.

What earns a place is the **finding**: "47 employees appear at two worksites in
the same month, and here is what we propose to do about each one." That is a
judgement that changes a number on a filed return, and it has to reach a human
and carry their answer back.

Three properties follow from that, and each is load-bearing:

**A finding is scoped like everything else.** Client, program, year. A finding
without a client cannot be acted on and cannot be audited.

**A resolution is durable.** The previous QC store was a module-level dict that
reset on restart. A decision that changes a filed figure cannot evaporate
because a container recycled.

**An unresolved finding is not a clean result.** `requires_decision` is counted
and surfaced rather than allowed to sit quietly in a list nobody opened.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_finding_resolution (
    finding_id   TEXT NOT NULL,
    client_id    INTEGER NOT NULL,
    tax_year     INTEGER NOT NULL,
    resolution   TEXT NOT NULL,
    detail       TEXT,
    note         TEXT,
    decided_by   TEXT NOT NULL,
    decided_at   TEXT NOT NULL,
    superseded_at TEXT,
    CHECK (resolution IN ('accept', 'assign', 'drop', 'flag'))
);

CREATE INDEX IF NOT EXISTS ix_finding_scope
    ON agent_finding_resolution (client_id, tax_year, finding_id);

-- One live decision per finding. A second would make "what did we decide?"
-- ambiguous at the moment it matters most.
CREATE UNIQUE INDEX IF NOT EXISTS ux_finding_one_live
    ON agent_finding_resolution (client_id, finding_id) WHERE superseded_at IS NULL;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class FindingResolution:
    """A human's answer to something an agent found."""

    finding_id: str
    client_id: int
    tax_year: int
    resolution: str          # accept | assign | drop | flag
    decided_by: str
    decided_at: str
    detail: dict[str, Any] | None = None   # e.g. which worksite to keep
    note: str | None = None
    superseded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "client_id": self.client_id,
            "tax_year": self.tax_year,
            "resolution": self.resolution,
            "detail": self.detail,
            "note": self.note,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "superseded_at": self.superseded_at,
        }


class SqliteFindingRepository:
    """Durable resolutions, alongside the claim store. [ADR-002]

    Append-only for the same reason `program_claim` is: "what did you decide, and
    when?" is an audit question, and an overwritten row cannot answer it.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        from infrastructure.persistence.sqlite_claims import _DEFAULT_PATH
        import os

        self.path = Path(path) if path else Path(os.getenv("OPERATIONAL_DB", _DEFAULT_PATH))
        self._local = threading.local()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _row(self, row: sqlite3.Row) -> FindingResolution:
        return FindingResolution(
            finding_id=row["finding_id"],
            client_id=row["client_id"],
            tax_year=row["tax_year"],
            resolution=row["resolution"],
            detail=json.loads(row["detail"]) if row["detail"] else None,
            note=row["note"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
            superseded_at=row["superseded_at"],
        )

    def live(self, client_id: int, tax_year: int | None = None) -> list[FindingResolution]:
        sql = (
            "SELECT * FROM agent_finding_resolution "
            "WHERE client_id = ? AND superseded_at IS NULL"
        )
        params: list[Any] = [client_id]
        if tax_year is not None:
            sql += " AND tax_year = ?"
            params.append(tax_year)
        return [self._row(r) for r in self._connect().execute(sql, params).fetchall()]

    def history(self, client_id: int, finding_id: str) -> list[FindingResolution]:
        rows = self._connect().execute(
            "SELECT * FROM agent_finding_resolution "
            "WHERE client_id = ? AND finding_id = ? ORDER BY decided_at, rowid",
            (client_id, finding_id),
        ).fetchall()
        return [self._row(r) for r in rows]

    def record(self, resolution: FindingResolution) -> FindingResolution:
        """Append, closing whatever it supersedes — one transaction."""
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE agent_finding_resolution SET superseded_at = ? "
                "WHERE client_id = ? AND finding_id = ? AND superseded_at IS NULL",
                (resolution.decided_at, resolution.client_id, resolution.finding_id),
            )
            conn.execute(
                "INSERT INTO agent_finding_resolution "
                "(finding_id, client_id, tax_year, resolution, detail, note, "
                " decided_by, decided_at, superseded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    resolution.finding_id,
                    resolution.client_id,
                    resolution.tax_year,
                    resolution.resolution,
                    json.dumps(resolution.detail) if resolution.detail else None,
                    resolution.note,
                    resolution.decided_by,
                    resolution.decided_at,
                ),
            )
        return resolution

    def reopen(self, client_id: int, finding_id: str, *, decided_by: str) -> None:
        """Withdraw the live decision, leaving the finding open again.

        The prior decision is closed rather than deleted: somebody decided
        something once, and that fact survives changing their mind.
        """
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE agent_finding_resolution SET superseded_at = ? "
                "WHERE client_id = ? AND finding_id = ? AND superseded_at IS NULL",
                (_now(), client_id, finding_id),
            )
