"""The typed source mapping: which physical table and column carries each logical field. [06]

The engine reads LOGICAL fields (`pay_period_start`, `account_id`); the lakehouse holds PHYSICAL
names that belong to whoever built it. This model is the one description of the link, so renaming a
table or a column, adding a prefix, changing case or dropping a field the engine does not use is a
file change, not a code change.

What a mapping can and cannot do
--------------------------------
Config only: physical table names and prefixes, column names and their case, type widening, dropping
an optional field, per-environment overrides (a mapping file may `extends` the default and say only
what differs). Needs code, or a NAMED TRANSFORM in `transforms.py` referenced from the mapping: a new
column the engine must use, a change in what a column means (`LocationId` versus
`WorksiteLocationId`, `PaycheckDate` versus another date), a different grain. A field the engine does
not know is refused at load, and a required field that is absent from the lake is a named error.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: A name becomes a path segment and a bracket-quoted SQL identifier; nothing else gets through.
IDENTIFIER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,127}$")
ARROW_TYPES = frozenset({"int64", "int32", "string", "bool", "double", "date32", "timestamp[us]", "decimal128(18, 2)"})
VERSION = 1


class MappingError(ValueError):
    """The mapping file is malformed or contradicts the fields the engine knows."""


@dataclass(frozen=True, slots=True)
class FieldMap:
    """One logical field: its physical column, Arrow type and whether the lake must carry it."""

    name: str
    column: str
    type: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class TableMap:
    """One logical entity: its physical table, tenant field, partition fields and fields."""

    logical: str
    table: str
    dataset_attr: str
    fields: dict[str, FieldMap]
    tenant_field: str | None = None
    partition_by: tuple[str, ...] = ()
    optional_reason: str | None = None

    def column(self, field_name: str) -> str:
        try:
            return self.fields[field_name].column
        except KeyError:
            raise MappingError(f"{self.logical}.{field_name} is not mapped") from None

    @property
    def tenant_column(self) -> str | None:
        return self.column(self.tenant_field) if self.tenant_field else None


@dataclass(frozen=True, slots=True)
class SourceMapping:
    """The whole mapping, validated at construction."""

    tables: dict[str, TableMap]
    case_insensitive: bool = True
    table_prefix: str = ""
    table_case: str = "as_is"
    transforms: dict[str, str] = field(default_factory=dict)
    origin: str = "default"

    def table(self, logical: str) -> TableMap:
        try:
            return self.tables[logical]
        except KeyError:
            raise MappingError(f"{logical!r} is not a logical table the engine reads") from None


def _field(table: str, name: str, raw: dict[str, Any], base: FieldMap | None) -> FieldMap:
    column = str(raw.get("column", base.column if base else ""))
    type_ = str(raw.get("type", base.type if base else ""))
    required = bool(raw.get("required", base.required if base else True))
    if not IDENTIFIER.match(column):
        raise MappingError(f"{table}.{name}: column {column!r} is not a plain identifier")
    if type_ not in ARROW_TYPES:
        raise MappingError(f"{table}.{name}: unknown type {type_!r}; one of {sorted(ARROW_TYPES)}")
    return FieldMap(name, column, type_, required)


def _table(logical: str, raw: dict[str, Any], base: TableMap | None) -> TableMap:
    known = base.fields if base else {}
    if base is None and not raw.get("dataset_attr"):
        raise MappingError(f"{logical}: a table the engine does not read cannot be added by configuration")
    fields = {n: f for n, f in known.items() if n not in raw.get("drop_fields", ())}
    for name in raw.get("drop_fields", ()):
        if name not in known:
            raise MappingError(f"{logical}.{name}: cannot drop a field the engine does not know")
        if known[name].required:
            raise MappingError(f"{logical}.{name} is required by the engine and cannot be dropped")
    for name, spec in (raw.get("fields") or {}).items():
        if base is not None and name not in known:
            raise MappingError(
                f"{logical}.{name}: the engine does not know this field. A new column the engine must use needs "
                "code (a field in the schema and a use in the projection), not configuration."
            )
        fields[name] = _field(logical, name, spec, known.get(name))
    table = str(raw.get("table", base.table if base else logical))
    if not IDENTIFIER.match(table):
        raise MappingError(f"{logical}: table {table!r} is not a plain identifier")
    return TableMap(
        logical=logical, table=table, dataset_attr=str(raw.get("dataset_attr", base.dataset_attr if base else "")),
        fields=fields, tenant_field=raw.get("tenant_field", base.tenant_field if base else None),
        partition_by=tuple(raw.get("partition_by", base.partition_by if base else ())),
        optional_reason=raw.get("optional_reason", base.optional_reason if base else None),
    )


def _check(mapping: SourceMapping) -> None:
    for table in mapping.tables.values():
        for ref in (table.tenant_field, *table.partition_by):
            if ref is not None and ref not in table.fields:
                raise MappingError(f"{table.logical}: {ref!r} (tenant or partition field) is not a mapped field")


def parse_mapping(data: dict[str, Any], base: SourceMapping | None = None, origin: str = "default") -> SourceMapping:
    """A mapping from its JSON form; with `base`, the file says only what differs from it."""
    if data.get("version", VERSION) != VERSION:
        raise MappingError(f"unsupported mapping version {data.get('version')!r}")
    naming = data.get("naming") or {}
    tables = dict(base.tables) if base else {}
    for logical, raw in (data.get("tables") or {}).items():
        tables[logical] = _table(logical, raw, tables.get(logical))
    mapping = SourceMapping(
        tables=tables,
        case_insensitive=bool(data.get("case_insensitive_columns", base.case_insensitive if base else True)),
        table_prefix=str(naming.get("table_prefix", base.table_prefix if base else "")),
        table_case=str(naming.get("table_case", base.table_case if base else "as_is")),
        transforms={**(base.transforms if base else {}), **(data.get("transforms") or {})},
        origin=origin,
    )
    _check(mapping)
    return mapping
