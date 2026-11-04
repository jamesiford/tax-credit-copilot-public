"""An in-memory SQLite database shaped like the semantic model, for executing built SQL offline.

One table per dataset in attached databases named like the deployed schemas, two clients
with distinguishable values, and rows the currency rules must hide. Running a built
statement here proves the SQL is valid for SQLite and that the tenant scope really isolates
clients; the T-SQL form is covered by string-level tests because no T-SQL engine runs offline.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from application.data.semantic_model import ColType, Column, Currency, Dataset, SchemaKey, SemanticModel
from infrastructure.persistence.tenant_sql import TenantScopedQuery

CLIENT_A, CLIENT_B = 1001, 2002
ROWS_PER_CLIENT = 4
_SCHEMAS = {SchemaKey.GOLD: "tcc_gold", SchemaKey.OPS: "tcc_ops", SchemaKey.SOURCE: "tcc_source"}


def _value(column: Column | None, physical: str, client: int, i: int, dataset: Dataset) -> Any:
    if physical in ("client_id", "AccountId"):
        return client
    if physical == "is_current":
        return 1
    if physical == "run_id":
        return f"run-{client}"
    if column is None:
        return 1
    if physical == "employee_id":
        return f"employee-{client}-{i}"  # one person per row, so a group's size is the count of its rows
    if physical == "LocationId" and dataset.name == "payroll":
        return i % 2 + 1  # two payroll sites with two people each: a group by location is not all singletons
    if column.choices:
        return column.choices[i % len(column.choices)] if column.logical == dataset.method_column else column.choices[0]
    return {
        ColType.INT: i, ColType.DECIMAL: i + 0.5, ColType.BOOL: 1, ColType.DATE: f"2023-01-0{i}",
        ColType.DATETIME: f"2023-01-0{i} 00:00:00",
        ColType.TEXT: f"{column.logical}-{client}-{i % 2}",
    }[column.type]


def _rows(dataset: Dataset, client: int) -> list[dict[str, Any]]:
    by_physical = {c.physical: c for c in dataset.columns if c.expression is None}
    physicals = sorted(dataset.physical_columns())
    rows = [{p: _value(by_physical.get(p), p, client, i + 1, dataset) for p in physicals} for i in range(ROWS_PER_CLIENT)]
    if dataset.currency is Currency.IS_CURRENT:
        rows.append({**rows[0], "is_current": 0})
    if dataset.currency is Currency.LIVE_RUN:
        rows.append({**rows[0], "run_id": f"old-{client}"})
    if dataset.name == "run_manifest":
        rows = [{**r, "run_status": "success", "superseded_by_run_id": None} for r in rows]
    return rows


def build_database(model: SemanticModel) -> sqlite3.Connection:
    """A connection with every dataset's table populated for two clients."""
    conn = sqlite3.connect(":memory:")
    for schema in _SCHEMAS.values():
        conn.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    for dataset in model.datasets:
        rows = [r for client in (CLIENT_A, CLIENT_B) for r in _rows(dataset, client)]
        _create(conn, dataset, rows)
    return conn


def _create(conn: sqlite3.Connection, dataset: Dataset, rows: list[dict[str, Any]]) -> None:
    name = f"{_SCHEMAS[dataset.schema]}.{dataset.table}"
    conn.execute(f"CREATE TABLE {name} ({', '.join(chr(34) + c + chr(34) for c in rows[0])})")
    _insert(conn, name, rows)


def _insert(conn: sqlite3.Connection, name: str, rows: list[dict[str, Any]]) -> None:
    columns = list(rows[0])
    marks = ", ".join("?" for _ in columns)
    conn.executemany(f"INSERT INTO {name} VALUES ({marks})", [[r[c] for c in columns] for r in rows])


def run(conn: sqlite3.Connection, sql: str, params: list[Any], client_id: int) -> list[tuple]:
    """Execute a built statement exactly as the production executor will: through the tenant helper."""
    statement, values = TenantScopedQuery(client_id).bind(sql, params)
    return conn.execute(statement, values).fetchall()
