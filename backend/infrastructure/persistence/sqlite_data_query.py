"""Execute a built data query on SQLite: tests and local `DATA_SOURCE=csv` runs. [CH-16c]

Same contract as the T-SQL adapters (read-only guard, tenant helper, row cap, typed timeout)
over a SQLite connection whose attached databases are named like the deployed schemas
(`tcc_gold`, `tcc_ops`, `tcc_source`), because that is how the builder's SQLite dialect writes
table names. Tests populate it from `tests/data_fixture.py`; a local run points
`DATA_QUERY_SQLITE_DIR` at a folder of `<schema>.db` files (`sqlite_data_source`).

The time limit is SQLite's progress handler, which interrupts the statement once the deadline
passes; the interrupt is reported as `QueryTimeout`, with no rows. One lock serialises queries:
this adapter is for a developer's machine, not for load.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from application.data.dialect import Dialect
from application.data.errors import QueryError
from application.data.exec_errors import QueryFailed, QueryTimeout
from application.data.executor import Rows, assert_read_only, read_capped
from infrastructure.persistence.tenant_sql import TenantScopeViolation, TenantScopedQuery

#: SQLite VM instructions between deadline checks: frequent enough to stop a runaway, rare enough to be free.
_CHECK_EVERY = 1000


class SqliteDataQueryExecutor:
    """Runs built SQLite statements for one client on a connection from `connect`."""

    dialect = Dialect.SQLITE

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect, self._lock = connect, threading.Lock()

    def execute(self, sql: str, params: Sequence[Any], *, client_id: int, timeout_s: float, max_rows: int) -> Rows:
        """Rows for the statement, or a typed `QueryError`. Never partial."""
        assert_read_only(sql)
        with self._lock:
            connection = self._connect()
            deadline = time.monotonic() + timeout_s
            connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, _CHECK_EVERY)
            try:
                return self._read(connection, sql, params, client_id, max_rows)
            except (QueryError, TenantScopeViolation):
                raise
            except sqlite3.OperationalError as exc:
                if "interrupted" in str(exc):
                    raise QueryTimeout(f"the query ran past its {timeout_s:g}s limit and was cancelled") from exc
                raise QueryFailed("the data source could not run the query") from exc
            finally:
                connection.set_progress_handler(None, 0)

    @staticmethod
    def _read(connection: sqlite3.Connection, sql: str, params: Sequence[Any], client_id: int, max_rows: int) -> Rows:
        cursor = connection.cursor()
        try:
            TenantScopedQuery(client_id).execute(cursor, sql, list(params))
            return read_capped(cursor, max_rows)
        finally:
            cursor.close()
