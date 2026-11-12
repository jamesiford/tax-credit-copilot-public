"""The resolver: the one place a consumer asks "where does this live?". [06.2]

The Delta reader, the writer, the SQL fast path, the governed data-query model, the tenant allow-list,
the grants and the tests all ask here, so a rename is made in one file (the default mapping, or the file
`SOURCE_MAPPING_FILE` names, which says only what differs from it).

`physical_table` keeps the interim settings working as overrides: `SOURCE_TABLE_MAP` (verbatim, wins),
then `SOURCE_TABLE_PREFIX` / `SOURCE_TABLE_CASE`, then the mapping's own `naming`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import get_settings

from .model import IDENTIFIER, MappingError, SourceMapping, TableMap, parse_mapping
from . import transforms

_DEFAULT_FILE = Path(__file__).with_name("default.json")
_CACHE: dict[tuple[str, int, int], SourceMapping] = {}


def _load(path: Path, base: SourceMapping | None, origin: str) -> SourceMapping:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _CACHE:
        _CACHE[key] = parse_mapping(json.loads(path.read_text(encoding="utf-8")), base, origin)
    return _CACHE[key]


def default_mapping() -> SourceMapping:
    """The shipped mapping: the logical contract and the plain (Pascal-cased) physical names."""
    return _load(_DEFAULT_FILE, None, "default")


def mapping() -> SourceMapping:
    """The mapping in force: the default, or the file `SOURCE_MAPPING_FILE` names layered over it."""
    named = get_settings().source_model.mapping_file
    if not named:
        return default_mapping()
    path = Path(named)
    if not path.is_file():
        raise MappingError(f"SOURCE_MAPPING_FILE {named!r} does not exist")
    return _load(path, default_mapping(), str(path))


def table_map(logical: str) -> TableMap:
    return mapping().table(logical)


def column(logical: str, field_name: str) -> str:
    """The physical column carrying `logical.field`."""
    return table_map(logical).column(field_name)


def tenant_column(logical: str) -> str | None:
    return table_map(logical).tenant_column


def tenant_columns() -> frozenset[str]:
    """Every physical tenant column the mapping names, for the data-query allow-list."""
    return frozenset(t.tenant_column for t in mapping().tables.values() if t.tenant_column)


def spec(logical: str) -> dict[str, str]:
    """`{field: arrow type}` for the fields this mapping carries (a dropped optional field is absent)."""
    return {name: f.type for name, f in table_map(logical).fields.items()}


def partition_columns(logical: str) -> list[str] | None:
    """The PHYSICAL partition columns of a table, or None."""
    table = table_map(logical)
    return [table.column(f) for f in table.partition_by] or None


def optional_tables() -> dict[str, str]:
    """Tables the headcount does not need, with what their absence costs."""
    return {t.logical: t.optional_reason for t in mapping().tables.values() if t.optional_reason}


def physical_table(logical: str) -> str:
    """The physical table name for `logical`, with the overrides applied."""
    source, current = get_settings().data_source, mapping()
    mapped = source.table_map.get(logical)
    if mapped is not None:
        name = mapped
    else:
        prefix = source.table_prefix or current.table_prefix
        case = source.table_case if source.table_case != "as_is" else current.table_case
        name = f"{prefix}{current.table(logical).table}"
        name = name.lower() if case == "lower" else name.upper() if case == "upper" else name
    if not IDENTIFIER.match(name):
        raise ValueError(
            f"physical table name {name!r} for {logical!r} is not a plain identifier; "
            "check the mapping and SOURCE_TABLE_PREFIX, SOURCE_TABLE_CASE and SOURCE_TABLE_MAP"
        )
    return name


def worksite_mode() -> str:
    chosen = get_settings().source_model.worksite_source or mapping().transforms.get("worksite_location", "worksite_then_location")
    return transforms.check("worksite_location", chosen)


def null_pay_date_mode() -> str:
    chosen = get_settings().source_model.null_pay_date or mapping().transforms.get("null_pay_date", "period_end")
    return transforms.check("null_pay_date", chosen)


def quoted(logical: str, field_name: str, alias: str = "") -> str:
    """A bracket-quoted SQL column reference (`p.[PayDate]`); the quoting is what makes reserved words safe."""
    ref = f"[{column(logical, field_name)}]"
    return f"{alias}.{ref}" if alias else ref


def describe() -> dict[str, Any]:
    """The effective mapping as plain data, for `validate-source-schema.py --print-effective`."""
    current = mapping()
    return {
        "origin": current.origin, "case_insensitive_columns": current.case_insensitive,
        "transforms": {"worksite_location": worksite_mode(), "null_pay_date": null_pay_date_mode()},
        "tables": {
            name: {
                "physical_table": physical_table(name), "tenant_column": table.tenant_column,
                "partition_by": partition_columns(name), "optional": bool(table.optional_reason),
                "columns": {f: {"column": m.column, "type": m.type, "required": m.required} for f, m in table.fields.items()},
            }
            for name, table in current.tables.items()
        },
    }
