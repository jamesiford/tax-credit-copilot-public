"""A SQLite connection factory over per-schema database files, for local runs. [CH-16c]

The builder's SQLite dialect writes `tcc_gold.<table>`, so the connection must have databases
attached under the deployed schema names. A local `DATA_SOURCE=csv` run points
`DATA_QUERY_SQLITE_DIR` at a folder holding `<schema>.db` for each schema; this attaches them.
Kept out of `sqlite_data_query.py` so that module executes nothing but tenant-bound statements.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from application.data.dialect import SchemaNames


def open_attached(directory: str | Path, schemas: SchemaNames) -> Callable[[], sqlite3.Connection]:
    """A connection factory over `<directory>/<schema>.db` files, attached under the deployed schema names."""
    root = Path(directory)
    holder: list[sqlite3.Connection] = []

    def connect() -> sqlite3.Connection:
        if not holder:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            for name in (schemas.gold, schemas.ops, schemas.source):
                conn.execute(f"ATTACH DATABASE ? AS {name}", (str(root / f"{name}.db"),))
            holder.append(conn)
        return holder[0]

    return connect
