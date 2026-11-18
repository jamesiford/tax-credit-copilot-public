"""The data map at run time: one resolver from logical to actual Warehouse names.

Statements spell tables as `{names.ops.run_manifest}`; the resolver returns the qualified
actual name (`tcc_ops.run_manifest` with the shipped map). An unknown logical name raises
`DataMapError` naming the key, so a typo fails loudly instead of reaching the database.

The map is read once at start-up (a restart picks up a change; there is no hot reload).
`DATA_MAP_FILE` names a complete map file; unset means the shipped default that sits next to
this module. The deprecated `GOLD_SCHEMA`, `OPS_SCHEMA` and `SOURCE_SCHEMA` variables
still override the schema names.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from data_map_load import DataMap, DataMapError, parse

DEFAULT_FILE = Path(__file__).resolve().parent / "data" / "data-map.default.json"


@lru_cache(maxsize=1)
def default_map() -> DataMap:
    """The shipped map; also the inventory a supplied file must match."""
    return parse(DEFAULT_FILE.read_bytes(), "embedded")


def load(path: str | None = None) -> DataMap:
    """Load `path` (complete, validated), or the shipped map when it is empty."""
    if not path or not path.strip():
        return default_map()
    try:
        raw = Path(path.strip()).read_bytes()
    except OSError as exc:
        raise DataMapError(f"The data map file '{path}' cannot be read: {exc}") from None
    return parse(raw, "file", default_map())


class _Schema:
    """`names.ops.run_manifest` -> the qualified actual name; unknown tables raise."""

    def __init__(self, data: DataMap, logical_schema: str) -> None:
        self._data, self._logical = data, logical_schema

    def __getattr__(self, table: str) -> str:
        if table.startswith("__"):
            raise AttributeError(table)
        return self._data_names(table)

    def _data_names(self, table: str) -> str:
        entry = self._data.tables.get(f"{self._logical}.{table}")
        if entry is None:
            raise DataMapError(f"warehouse.tables.{self._logical}.{table} is not a known key.")
        schema = self._data.gold_schema if self._logical == "gold" else self._data.ops_schema
        return f"{schema}.{entry['table']}"

    def __call__(self, table: str) -> str:
        return self._data_names(table)


class Names:
    """Logical-name accessors over one `DataMap`: `names.gold.x`, `names.ops.x`, `names.source_schema`."""

    def __init__(self, data: DataMap) -> None:
        self.map = data
        self.gold = _Schema(data, "gold")
        self.ops = _Schema(data, "ops")

    @property
    def migration_table(self) -> str:
        """The actual name of the migration bookkeeping table (the map may rename it)."""
        return self.map.tables["ops.schema_migration"]["table"]

    @property
    def source_schema(self) -> str:
        return self.map.source_schema


def build(path: str | None, overrides: dict[str, str] | None = None) -> DataMap:
    """The process's map: `path` (or the shipped default), with schema names the deprecated variables override."""
    from dataclasses import replace

    data = load(path)
    return replace(data, **overrides) if overrides else data
