"""An emulated Fabric lakehouse SQL analytics endpoint, for offline tests and the read-path spike. [10]

`FakeLakehouseSql(root)` loads every Delta table under `<root>/Tables/<schema>/` into an in-memory SQLite
database and answers the two statement shapes the SQL read path sends (`INFORMATION_SCHEMA.COLUMNS`, and a
projected `SELECT` with `WHERE col = ?` or `col IN (?, ...)`). Three-part names are reduced to the table name.

It stands in for the endpoint's SHAPE and for the types ODBC hands back (Decimal, date, datetime, int, str,
bool): decimals and dates are stored as text and converted on the way out, so a parity test sees what pyodbc
would give. It says nothing about the endpoint's speed, its type spellings or its metadata sync; those are live
checks. It counts statements, rows and an approximate payload so a benchmark can report round trips.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
from deltalake import DeltaTable

from data.source import onelake
from data.source.to_delta import TABLE_SPECS

_THREE_PART = re.compile(r"\[[^\]]+\]\.(?:\[[^\]]+\])?\.(\[[^\]]+\])")
_FROM = re.compile(r"FROM\s+\[([^\]]+)\]", re.IGNORECASE)


def _kind(arrow_type: pa.DataType) -> str:
    if pa.types.is_decimal(arrow_type):
        return "decimal"
    if pa.types.is_date(arrow_type):
        return "date"
    if pa.types.is_timestamp(arrow_type):
        return "datetime"
    if pa.types.is_boolean(arrow_type):
        return "bool"
    if pa.types.is_integer(arrow_type):
        return "int"
    if pa.types.is_floating(arrow_type):
        return "float"
    return "str"


def _store(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _restore(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "decimal":
        return Decimal(value)
    if kind == "date":
        return date.fromisoformat(value)
    if kind == "datetime":
        return datetime.fromisoformat(value)
    if kind == "bool":
        return bool(value)
    return value


class _Cursor:
    def __init__(self, endpoint: "FakeLakehouseSql") -> None:
        self._endpoint = endpoint
        self._cursor = endpoint.db.cursor()
        self._kinds: list[str] = []
        self._columns_rows: list[tuple] | None = None
        self.timeout = 0

    def execute(self, sql: str, params: Any = None) -> None:
        params = list(params or [])
        self._endpoint.statements.append((sql, list(params)))
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            schema, table = params
            self._columns_rows = [(c,) for c in self._endpoint.columns.get((schema, table), [])]
            return
        self._columns_rows = None
        reduced = _THREE_PART.sub(r"\1", sql)
        table = _FROM.search(reduced).group(1)
        self._cursor.execute(reduced, params)
        names = [d[0] for d in self._cursor.description]
        self._kinds = [self._endpoint.kinds[table][n] for n in names]

    def fetchmany(self, size: int) -> list[tuple]:
        if self._columns_rows is not None:
            rows, self._columns_rows = self._columns_rows, []
            return rows
        batch = self._cursor.fetchmany(size)
        out = [tuple(_restore(v, k) for v, k in zip(row, self._kinds)) for row in batch]
        self._endpoint.rows_sent += len(out)
        self._endpoint.payload_chars += sum(len(str(v)) for row in batch for v in row)
        return out

    def fetchall(self) -> list[tuple]:
        return self.fetchmany(1 << 30)

    def close(self) -> None:
        self._cursor.close()


class _Live:
    def __init__(self, endpoint: "FakeLakehouseSql") -> None:
        self._endpoint = endpoint

    def cursor(self) -> _Cursor:
        return _Cursor(self._endpoint)


class FakeLakehouseSql:
    """The endpoint over the Delta tables under `root` (`Tables/<schema>/<physical>`)."""

    def __init__(self, root: Path, *, schema: str = "dbo", skip: tuple[str, ...] = ()) -> None:
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.columns: dict[tuple[str, str], list[str]] = {}
        self.kinds: dict[str, dict[str, str]] = {}
        self.statements: list[tuple[str, list]] = []
        self.rows_sent = 0
        self.payload_chars = 0
        for table in TABLE_SPECS:
            physical = onelake.physical_table(table)
            path = Path(root) / "Tables" / schema / physical if schema else Path(root) / "Tables" / physical
            if table in skip or not path.exists():
                continue
            self._load(schema or "dbo", physical, DeltaTable(str(path)).to_pyarrow_table())

    def _load(self, schema: str, physical: str, arrow: pa.Table) -> None:
        names = arrow.column_names
        self.columns[(schema, physical)] = names
        self.kinds[physical] = {n: _kind(arrow.schema.field(n).type) for n in names}
        quoted = ", ".join(f"[{n}]" for n in names)
        self.db.execute(f"CREATE TABLE [{physical}] ({quoted})")
        records = [tuple(_store(v) for v in row) for row in zip(*(arrow[n].to_pylist() for n in names))]
        self.db.executemany(f"INSERT INTO [{physical}] VALUES ({','.join('?' * len(names))})", records)

    @contextmanager
    def connect(self) -> Iterator[_Live]:
        yield _Live(self)

    def reset_counters(self) -> None:
        self.statements.clear()
        self.rows_sent = 0
        self.payload_chars = 0
