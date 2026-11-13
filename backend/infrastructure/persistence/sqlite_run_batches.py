"""The run batch queue over SQLite: local development and tests. [ADR-012]

The same tables as the Warehouse (migration 0004) and the same store code; only the transaction and the
instant encoding differ. A write transaction is `BEGIN IMMEDIATE` under a process lock, so a claim here is
airtight, which the Warehouse's is not (see `run_batch_store`).
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from config import get_settings
from infrastructure.persistence.run_batch_queue import RunBatchRepository

T = TypeVar("T")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_batch (
    batch_id TEXT PRIMARY KEY, kind TEXT NOT NULL, scope_kind TEXT NOT NULL, scope_spec TEXT NOT NULL,
    program_code TEXT, tax_years TEXT, force_run INTEGER NOT NULL, include_code_commit INTEGER NOT NULL,
    refresh_once INTEGER NOT NULL, status TEXT NOT NULL, cancel_requested INTEGER NOT NULL, items_total INTEGER NOT NULL,
    items_queued INTEGER NOT NULL, items_running INTEGER NOT NULL, items_succeeded INTEGER NOT NULL,
    items_skipped INTEGER NOT NULL, items_failed INTEGER NOT NULL, items_cancelled INTEGER NOT NULL,
    requested_by TEXT NOT NULL, requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
    idempotency_key TEXT, dry_run_summary TEXT);
CREATE TABLE IF NOT EXISTS run_batch_item (
    item_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, seq INTEGER NOT NULL, client_id INTEGER NOT NULL,
    program_code TEXT, tax_year INTEGER, status TEXT NOT NULL, attempts INTEGER NOT NULL, lease_owner TEXT,
    lease_expires_at TEXT, heartbeat_at TEXT, not_before TEXT, run_id TEXT, skip_reason TEXT, error_dependency TEXT,
    error_message TEXT, started_at TEXT, finished_at TEXT);
"""


class _Result:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int) -> None:
        self.rows, self.rowcount = rows, rowcount


class _Tx:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: list[Any] | tuple = ()) -> _Result:
        cursor = self._conn.execute(sql, list(params))
        rows = [dict(r) for r in cursor.fetchall()] if cursor.description else []
        return _Result(rows, cursor.rowcount)


class SqliteBackend:
    """SQLite transactions and ISO-string instants."""
    def __init__(self, path: str | Path | None = None, schema: str = _SCHEMA) -> None:
        from infrastructure.persistence.sqlite_claims import _DEFAULT_PATH

        chosen = path or get_settings().stores.operational_db_or(_DEFAULT_PATH)
        if str(chosen) != ":memory:":
            Path(chosen).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(chosen), check_same_thread=False, isolation_level=None, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(schema)

    def table(self, name: str) -> str:
        return name

    def bind(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="milliseconds")

    def parse(self, value: Any) -> datetime | None:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None

    def page(self, limit: int, offset: int) -> tuple[str, list[int]]:
        return "LIMIT ? OFFSET ?", [limit, offset]

    def transact(self, work: Callable[[_Tx], T]) -> T:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                result = work(_Tx(self._conn))
                self._conn.execute("COMMIT")
                return result
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        self._conn.close()


class SqliteRunBatchRepository(RunBatchRepository):
    """The whole queue port over a SQLite file or memory."""
    def __init__(self, path: str | Path | None = None) -> None:
        self._backend = SqliteBackend(path)
        super().__init__(self._backend)

    def close(self) -> None:
        self._backend.close()
