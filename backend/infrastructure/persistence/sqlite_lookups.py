"""`LookupOverrideStore` over SQLite: local runs and tests. [07]

The same two tables as the Warehouse (`lookup_override`, `lookup_audit`, migration 0003), append-style: a new value for a
key closes the live row (`superseded_at`) and inserts itself; a removal closes without inserting; every change also
appends an audit row. Nothing is ever deleted, so "what did we say this code meant in March, and who said so?" has
an answer.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from config import get_settings
from data.lookups.store import OverrideEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lookup_override (
    override_id TEXT PRIMARY KEY, lookup_name TEXT NOT NULL, client_id INTEGER NOT NULL, key_kind TEXT NOT NULL,
    key_value TEXT NOT NULL, value_json TEXT NOT NULL, effective_from TEXT, effective_to TEXT, authored_by TEXT NOT NULL,
    authored_on TEXT NOT NULL, basis TEXT, inferred INTEGER NOT NULL, superseded_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_lookup_one_live ON lookup_override (lookup_name, client_id, key_kind, key_value)
    WHERE superseded_at IS NULL;
CREATE TABLE IF NOT EXISTS lookup_audit (
    audit_id TEXT PRIMARY KEY, lookup_name TEXT NOT NULL, client_id INTEGER NOT NULL, action TEXT NOT NULL,
    key_kind TEXT NOT NULL, key_value TEXT NOT NULL, value_json TEXT, actor TEXT NOT NULL, at TEXT NOT NULL, basis TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class SqliteLookupStore:
    """Durable app-owned lookup rows, and their audit trail."""

    is_durable = True

    def __init__(self, path: str | Path | None = None) -> None:
        from infrastructure.persistence.sqlite_claims import _DEFAULT_PATH

        chosen = path or get_settings().stores.operational_db_or(_DEFAULT_PATH)
        self.path, self._local = Path(chosen), threading.local()
        if str(chosen) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._local.conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
        return conn

    def entries(self, lookup: str, client_id: int) -> list[OverrideEntry]:
        rows = self._connect().execute(
            "SELECT * FROM lookup_override WHERE lookup_name = ? AND client_id IN (?, 0) AND superseded_at IS NULL "
            "ORDER BY client_id DESC, key_kind, key_value", [lookup, client_id],
        ).fetchall()
        return [OverrideEntry(
            r["lookup_name"], r["client_id"], r["key_kind"], r["key_value"], r["value_json"], r["authored_by"],
            r["basis"] or "", bool(r["inferred"]), _day(r["effective_from"]), _day(r["effective_to"]),
        ) for r in rows]

    def _audit(self, conn: sqlite3.Connection, action: str, record: tuple, actor: str, basis: str = "") -> None:
        """`record` is (lookup, client_id, key_kind, key, value)."""
        conn.execute("INSERT INTO lookup_audit VALUES (?,?,?,?,?,?,?,?,?,?)",
                     [str(uuid.uuid4()), record[0], record[1], action, *record[2:], actor, _now(), basis])

    def put(self, entry: OverrideEntry) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE lookup_override SET superseded_at = ? WHERE lookup_name = ? AND client_id = ? AND key_kind = ? "
                "AND key_value = ? AND superseded_at IS NULL", [now, entry.lookup, entry.client_id, entry.key_kind, entry.key])
            conn.execute(
                "INSERT INTO lookup_override VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                [str(uuid.uuid4()), entry.lookup, entry.client_id, entry.key_kind, entry.key, entry.value,
                 entry.effective_from.isoformat() if entry.effective_from else None,
                 entry.effective_to.isoformat() if entry.effective_to else None, entry.authored_by, now, entry.basis,
                 int(entry.inferred)])
            self._audit(conn, "put", (entry.lookup, entry.client_id, entry.key_kind, entry.key, entry.value), entry.authored_by, entry.basis)

    def remove(self, lookup: str, client_id: int, key_kind: str, key: str, actor: str) -> bool:
        with self._connect() as conn:
            closed = conn.execute(
                "UPDATE lookup_override SET superseded_at = ? WHERE lookup_name = ? AND client_id = ? AND key_kind = ? "
                "AND key_value = ? AND superseded_at IS NULL", [_now(), lookup, client_id, key_kind, key]).rowcount
            if closed:
                self._audit(conn, "remove", (lookup, client_id, key_kind, key, None), actor)
        return bool(closed)

    def audit(self, lookup: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM lookup_audit", []
        if lookup:
            sql, params = sql + " WHERE lookup_name = ?", [lookup]
        return [dict(r) for r in self._connect().execute(sql + " ORDER BY rowid", params).fetchall()]
