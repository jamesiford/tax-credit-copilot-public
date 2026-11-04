"""Fakes for the data-query adapters: a scripted T-SQL connection and a SQLite harness. [CH-16c]

No T-SQL engine runs offline, so the Warehouse and Lakehouse adapters are tested against a fake
that records what reached the cursor (the bound statement, the parameters, the timeout set) and
replays scripted rows or errors. `Harness` gives the contract suite one shape across adapters.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any

from application.data.executor import DataQueryExecutor
from infrastructure.persistence.lakehouse_data_query import LakehouseDataQueryExecutor
from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
from infrastructure.persistence.warehouse_data_query import WarehouseDataQueryExecutor

CLIENT = 1001
OTHER = 2002


class DriverError(Exception):
    """Shaped like a pyodbc error: the SQLSTATE is `args[0]`."""


class FakeCursor:
    def __init__(self, live: "FakeLive") -> None:
        self._live, self.description, self._rows = live, None, []

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        self._live.executed.append((sql, list(params or [])))
        self._live.timeouts_seen.append(self._live.timeout)
        if self._live.error is not None:
            raise self._live.error
        self.description = [("v",)]
        self._rows = [(i,) for i in range(self._live.row_count)]

    def fetchmany(self, n: int) -> list[tuple]:
        return self._rows[:n]

    def close(self) -> None:
        self._live.cursors_closed += 1


class FakeLive:
    """What `pyodbc.connect` returns: a connection with a settable `timeout`."""

    def __init__(self) -> None:
        self.timeout, self.executed, self.timeouts_seen = 0, [], []
        self.row_count, self.error, self.cursors_closed = 0, None, 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


class FakeTsqlConnection:
    """The slice of `FabricWarehouseConnection` the executor uses."""

    def __init__(self, *, configured: bool = True) -> None:
        self.live, self.configured, self.failed = FakeLive(), configured, False

    def require_configuration(self) -> None:
        if not self.configured:
            from infrastructure.persistence.fabric_warehouse import WarehouseNotConfigured

            raise WarehouseNotConfigured("not set")

    @contextmanager
    def connect(self):
        try:
            yield self.live
        except Exception:
            self.failed = True
            raise


class Harness:
    """One adapter under test, with the same knobs whatever its engine."""

    name = ""
    statement = "SELECT v FROM data_t WHERE {tenant} ORDER BY v"

    def executor(self) -> DataQueryExecutor: ...
    def seed(self, rows: int) -> None: ...
    def slow(self) -> str: ...
    def broken(self) -> None: ...
    def bound(self) -> tuple[str, list[Any]] | None: ...


class TsqlHarness(Harness):
    def __init__(self, kind: str) -> None:
        self.name, self.connection = kind, FakeTsqlConnection()
        self._cls = WarehouseDataQueryExecutor if kind == "warehouse" else LakehouseDataQueryExecutor

    def executor(self) -> DataQueryExecutor:
        return self._cls(self.connection)

    def seed(self, rows: int) -> None:
        self.connection.live.row_count = rows

    def slow(self) -> str:
        self.connection.live.error = DriverError("HYT00", "[HYT00] Query timeout expired (0) (SQLExecDirectW)")
        return self.statement

    def broken(self) -> None:
        self.connection.live.error = DriverError("42S02", "Invalid object name 'secret_table'")

    def bound(self):
        return self.connection.live.executed[-1] if self.connection.live.executed else None


class SqliteHarness(Harness):
    def __init__(self) -> None:
        self.name = "sqlite"
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.execute("CREATE TABLE data_t (client_id INTEGER, v INTEGER)")
        self.last: tuple[str, list[Any]] | None = None

    def executor(self) -> DataQueryExecutor:
        return SqliteDataQueryExecutor(lambda: self.conn)

    def seed(self, rows: int) -> None:
        self.conn.executemany("INSERT INTO data_t VALUES (?, ?)", [(CLIENT, i) for i in range(rows)])
        self.conn.execute("INSERT INTO data_t VALUES (?, ?)", (OTHER, 999))

    def slow(self) -> str:
        self.conn.executemany("INSERT INTO data_t VALUES (?, ?)", [(CLIENT, i) for i in range(1500)])
        return "SELECT COUNT(*) FROM data_t a, data_t b, data_t c WHERE {tenant:a} AND b.client_id = a.client_id"

    def broken(self) -> None:
        self.conn.execute("DROP TABLE data_t")

    def bound(self):
        return None


def harnesses() -> list[Harness]:
    return [SqliteHarness(), TsqlHarness("warehouse"), TsqlHarness("lakehouse")]
