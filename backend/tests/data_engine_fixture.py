"""A Gold store populated by the REAL engine run, in SQLite, with the real reader on top. [CH-16e]

The semantic model's overlapping measures (eligible counts per method, credit per tax year,
headcount per month) are only trustworthy if the generic query returns what the fixed
capabilities return. So nothing here is a hand-built row:

- `RunClientCalculationCommand` replays the synthetic payroll through the certified engine;
- the real `GoldWriter` writes the run (its statements, its supersession, its manifest stamp)
  to a SQLite connection whose attached databases carry the deployed schema names;
- the real `GoldReader` answers the fixed capabilities from that same store, its own
  statements translated from T-SQL's `TOP`/`OFFSET ... FETCH` to SQLite's `LIMIT`/`OFFSET`
  and nothing else;
- the data query service reads the same connection through the SQLite adapter.

Two honest differences from the deployed path: SQLite stores money as a float (the engine's
money is whole dollars, so values are exact and tests compare as Decimals), and the writer's
post-write section-9 validation is T-SQL and is skipped. It is not part of what these tests
prove.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from application.data.semantic_model import Source, default_model
from application.data.service import DataQueryService
from infrastructure.persistence.gold_reader import GoldReader, _rows
from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
from infrastructure.persistence.warehouse_gold import GoldWriter
from tools import gold_projection as gp

CLIENT = 1001
YEAR = 2025
_GOLD_TABLES = {
    "employee_period_fact": gp.EMPLOYEE_PERIOD_FACT_COLUMNS, "employee_eligibility": gp.EMPLOYEE_ELIGIBILITY_COLUMNS,
    "onezero_matrix": gp.ONEZERO_MATRIX_COLUMNS, "unit_month_summary": gp.UNIT_MONTH_SUMMARY_COLUMNS,
    "run_method_summary": gp.RUN_METHOD_SUMMARY_COLUMNS, "unit_year_master": gp.UNIT_YEAR_MASTER_COLUMNS,
    "unit_credit_installment": gp.UNIT_CREDIT_INSTALLMENT_COLUMNS,
}
_TOP = re.compile(r"SELECT TOP (\d+) ", re.IGNORECASE)
_PAGE = re.compile(r"OFFSET \? ROWS FETCH NEXT \? ROWS ONLY", re.IGNORECASE)


def _bindable(value: Any) -> Any:
    """What SQLite can store: it has no decimal, date or bool-subclass binding it will not warn about."""
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return value


class _Cursor:
    """A cursor that binds engine values (Decimal, date) the way SQLite can take them."""

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    def execute(self, sql: str, params: Any = ()) -> "_Cursor":
        self._cursor.execute(sql, [_bindable(p) for p in params])
        return self

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _Connection:
    """The one SQLite connection the writer, the reader and the data service share."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        self.raw = raw

    def cursor(self) -> _Cursor:
        return _Cursor(self.raw.cursor())

    def commit(self) -> None:
        self.raw.commit()

    def close(self) -> None:
        """Kept open: the in-memory database IS the store, so closing it would erase the run."""


class SqliteWarehouse:
    """Stands where `FabricWarehouseConnection` stands, over an in-memory database."""

    def __init__(self) -> None:
        raw = sqlite3.connect(":memory:", check_same_thread=False)
        for schema in ("tcc_gold", "tcc_ops", "tcc_source"):
            raw.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
        self.connection = _Connection(raw)
        for table, columns in _GOLD_TABLES.items():
            raw.execute(f"CREATE TABLE tcc_gold.{table} ({', '.join(columns)})")
        raw.execute(f"CREATE TABLE tcc_ops.run_manifest ({', '.join(gp_manifest_columns())})")

    def open(self) -> _Connection:
        return self.connection

    @contextmanager
    def connect(self):
        yield self.connection

    @contextmanager
    def scope(self):
        yield self.connection


def gp_manifest_columns() -> tuple[str, ...]:
    from infrastructure.persistence.fabric_warehouse import _MANIFEST_COLUMNS

    return tuple(_MANIFEST_COLUMNS)


class OfflineGoldWriter(GoldWriter):
    """The real writer; only its T-SQL-only post-write validation is skipped (see the module docstring)."""

    def validate(self) -> list[dict[str, Any]]:
        return []


def _translate(sql: str, values: list[Any]) -> tuple[str, list[Any]]:
    """T-SQL row limits to SQLite's: the one change the reader's own statements need."""
    top = _TOP.search(sql)
    if top:
        sql = f"{_TOP.sub('SELECT ', sql, count=1).rstrip()} LIMIT {int(top.group(1))}"
    if _PAGE.search(sql):
        sql = _PAGE.sub("LIMIT ? OFFSET ?", sql)
        values = [*values[:-2], values[-1], values[-2]]
    return sql, values


class SqliteGoldReader(GoldReader):
    """The real `GoldReader`: its statements and its value coercion, run on SQLite."""

    def __init__(self, warehouse: SqliteWarehouse) -> None:
        super().__init__(connection=warehouse)  # type: ignore[arg-type]
        self._raw = warehouse.connection.raw

    def _run(self, statement: tuple[str, list[Any]]) -> list[dict[str, Any]]:
        sql, values = _translate(*statement[:1], list(statement[1]))
        cursor = self._raw.cursor()
        try:
            cursor.execute(sql, [_bindable(v) for v in values])
            return _rows(cursor)
        finally:
            cursor.close()

    def _many(self, statement):
        return self._run(statement)

    def _batch(self, statements):
        return [self._run(s) for s in statements]


def run_engine(warehouse: SqliteWarehouse, tmp_dir: Any, claims: Any = None) -> None:
    """Replay the synthetic payroll through the real command, writing to `warehouse` with the real writer.

    The command also records a claim and reads saved base years, so both stores are private to the call
    (see `test_run_client_calculation`): nothing here may reach the operational database. A caller that
    wants the claim the run recorded passes its own `claims` repository and keeps it open.
    """
    from application import wiring
    from application.commands.run_client_calculation import RunClientCalculationCommand
    from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    kept = claims is not None
    claims, original = claims if kept else SqliteClaimRepository(tmp_dir / "claims.db"), wiring.get_claim_repository()
    wiring.set_gold_writer(OfflineGoldWriter(warehouse))  # type: ignore[arg-type]
    wiring.set_claim_repository(claims)
    wiring.set_override_repository(InMemoryManualOverrideRepository())
    try:
        wiring.get_mediator().send(RunClientCalculationCommand(client_id=CLIENT, tax_year=YEAR, state="GA", actor="tests"))
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        if not kept:
            claims.close()


def data_service(warehouse: SqliteWarehouse) -> DataQueryService:
    """The data query service over the same store the fixed capabilities read."""
    executor = SqliteDataQueryExecutor(lambda: warehouse.connection.raw)
    return DataQueryService(default_model(), {Source.WAREHOUSE: executor, Source.LAKEHOUSE: executor})
