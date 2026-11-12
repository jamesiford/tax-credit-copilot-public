"""The SQL-analytics-endpoint read of one source table: a spike behind `SOURCE_READ_MODE=sql`. [10]

The OneLake read (`from_fabric._scan`) opens Delta files, which needs a workspace role that can read files
(Contributor or higher). A Fabric Viewer can reach only the SQL analytics endpoint. This module answers the same
question over that endpoint, for the same tables, with the same columns, and hands back the same thing: a list of
dicts keyed by LOGICAL field name. Everything above it (the mapping, coercion, key sets, the projection to engine
rows, the cache) is the code the OneLake path already runs, so any difference between the two modes is a difference
in what this module returns, and the parity tests compare exactly that.

What it does, and does not do:

- One projected statement per read: the engine's columns only, `WHERE tenant = ?` for a tenant read or batched
  `IN (...)` lists for a keyed read (each batch under SQL Server's 2,100-parameter ceiling), never `SELECT *`.
- Rows are streamed with `fetchmany` and turned into dicts as they arrive, so the driver never holds a second
  copy of a large result, and the account-size guard stops the read at the limit instead of after it.
- Columns are discovered from `INFORMATION_SCHEMA.COLUMNS`, then resolved by the same mapping as the Delta path.
  A table with no columns is an absent table, reported as the same `TableNotFoundError` the optional-table
  handling already catches.
- It records NO data version: the endpoint exposes no Delta version, so cache entries are not invalidated by a
  reload until they age out. Design note: docs/architecture/SQL-READ-PATH.md.
"""
from __future__ import annotations

import time
from typing import Any

from config import get_settings

from . import read_stats
from .mapping import engine_fields, table_map
from .onelake import physical_table, sql_table_name

#: Rows per `fetchmany`: large enough that round trips are not the cost, small enough that a batch is a few MB.
FETCH_SIZE = 50_000
#: Ids per `IN (...)` statement: under SQL Server's 2,100-parameter ceiling with headroom for other parameters.
ID_BATCH = 900

_COLUMNS_SQL = (
    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION"
)


def read_mode() -> str:
    """`SOURCE_READ_MODE`: `onelake` (the default) or `sql`."""
    return get_settings().source_model.read_mode


def _connection() -> Any:
    """The lakehouse endpoint's connection, bound by `bootstrap/source_binding.py`."""
    from application.services import resolve

    return resolve("lakehouse_sql")()


def _quote(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def _schema_of(reader: Any) -> str:
    return reader.schema or "dbo"


def _columns(live: Any, reader: Any, table: str) -> list[str]:
    """The table's actual column names, in order; empty when the table does not exist."""
    cursor = live.cursor()
    try:
        cursor.execute(_COLUMNS_SQL, [_schema_of(reader), physical_table(table)])
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


def table_exists(reader: Any, table: str) -> bool:
    """Whether the endpoint has this table (used where an optional table's absence must be told from an outage)."""
    with _connection().connect() as live:
        return bool(_columns(live, reader, table))


def _statements(qualified: str, select: str, found: dict[str, str], tenant_field: str | None, tenant: int | None, key: str | None, ids: set | None) -> list[tuple[str, list]]:
    """The statements for one read: a tenant filter, batched key lists, or (no filter) the whole table."""
    if tenant is not None and tenant_field in found:
        return [(f"SELECT {select} FROM {qualified} WHERE {_quote(found[tenant_field])} = ?", [tenant])]
    if key is not None and key in found:
        ordered = sorted(ids or ())
        batches = [ordered[i:i + ID_BATCH] for i in range(0, len(ordered), ID_BATCH)]
        return [(f"SELECT {select} FROM {qualified} WHERE {_quote(found[key])} IN ({','.join('?' * len(b))})", b) for b in batches]
    return [(f"SELECT {select} FROM {qualified}", [])]


def _fetch(live: Any, statements: list[tuple[str, list]], names: list[str], limit: int | None) -> tuple[list[dict[str, Any]], int]:
    """Run each statement, streaming rows into dicts; returns the rows and the statement count. Stops at `limit`."""
    rows: list[dict[str, Any]] = []
    for sql, params in statements:
        cursor = live.cursor()
        try:
            cursor.execute(sql, params)
            while True:
                batch = cursor.fetchmany(FETCH_SIZE)
                if not batch:
                    break
                rows.extend(dict(zip(names, record)) for record in batch)
                if limit is not None and len(rows) > limit:
                    return rows, len(statements)
        finally:
            cursor.close()
    return rows, len(statements)


def scan(reader: Any, table: str, *, tenant: int | None = None, key: str | None = None, ids: set | None = None) -> list[dict[str, Any]]:
    """The SQL counterpart of `FabricLakehouseReader._scan`: same arguments, same return shape."""
    from deltalake.exceptions import TableNotFoundError

    started = time.perf_counter()
    qualified = sql_table_name(reader.lakehouse, reader.schema, table)
    from . import from_fabric

    uri = f"sql://{qualified}"
    with _connection().connect() as live:
        found = from_fabric._COLUMN_CACHE.get(uri)
        if found is None:  # discovered once per process; an absent table is never cached, so it is asked about each time
            actual = _columns(live, reader, table)
            if not actual:
                raise TableNotFoundError(qualified)
            found = reader._columns_of(table, uri, actual)
        wanted = engine_fields(table) | {n for n in (table_map(table).tenant_field, key) if n}
        pairs = [(name, col) for name, col in found.items() if name in wanted]
        select = ", ".join(_quote(col) for _, col in pairs)
        tenant_field = table_map(table).tenant_field
        scoped = tenant is not None and tenant_field in found
        statements = _statements(qualified, select, found, tenant_field, tenant, key, ids)
        limit = get_settings().source_model.max_account_rows if scoped else None
        rows, trips = _fetch(live, statements, [n for n, _ in pairs], limit)
    if scoped and limit is not None and len(rows) > limit:
        from application.errors import AccountTooLarge

        raise AccountTooLarge(tenant, len(rows), limit)
    read_stats.record_read(table, len(rows), 0, len(pairs), time.perf_counter() - started, filtered=scoped or key is not None)
    return rows

