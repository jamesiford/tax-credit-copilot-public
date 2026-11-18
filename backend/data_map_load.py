"""Read and validate a complete data map (docs/data/data-map.json) into an immutable `DataMap`.

Why: the customer names every database, schema, table and column once, in one file. The
same file and the same rules are enforced by the .NET host (`DataMapLoader`), so a map
that starts one host starts the other. A supplied file is COMPLETE, not a patch: it must
list exactly the logical entries the shipped map lists, or loading names the first
missing or unknown key. Warehouse column renaming is refused until it is implemented,
because a map that is silently ignored is worse than one that is rejected.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]{0,127}$")
PREFIX = re.compile(r"^[A-Za-z0-9_\-]{0,64}$")


class DataMapError(ValueError):
    """The data map is malformed, incomplete or contradicts itself; the message names the key."""


@dataclass(frozen=True, slots=True)
class DataMap:
    """The validated map: actual names behind the logical names the code speaks."""

    source: str  # "embedded" | "file"
    sha256: str
    source_database: str | None
    warehouse_database: str | None
    source_schema: str
    gold_schema: str
    ops_schema: str
    tables: dict[str, dict[str, Any]]  # "ops.run_manifest" -> {"schema", "table", "columns": {logical: actual}}
    lakehouse: dict[str, Any]  # the `lakehouse` section, as authored


def _keys(obj: Any, path: str, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise DataMapError(f"{path or 'the data map'} must be an object.")
    live = {k: v for k, v in obj.items() if not k.startswith("_")}
    for key in live:
        if key not in required and key not in optional:
            raise DataMapError(f"{_join(path, key)} is not a known key.")
    for key in required:
        if key not in live:
            raise DataMapError(f"{_join(path, key)} is missing.")
    return live


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _ident(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise DataMapError(f"{path} must be a name (an unmatched entry still has a null value).")
    if not IDENTIFIER.match(value):
        raise DataMapError(f"{path} '{value}' is not a plain identifier (no quotes or brackets).")
    return value


def _database_name(section: dict[str, Any], path: str) -> str | None:
    db = _keys(section["database"], f"{path}.database", ("logical", "name"))
    return None if db["name"] is None else _ident(db["name"], f"{path}.database.name")


def _warehouse_tables(tables: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    taken: dict[str, str] = {}
    for key, node in _keys(tables, "warehouse.tables", (), tuple(tables)).items():
        path = f"warehouse.tables.{key}"
        t = _keys(node, path, ("schema", "table", "columns"))
        schema, _, logical = key.partition(".")
        if schema not in ("gold", "ops") or t["schema"] != schema or not logical:
            raise DataMapError(f"{path}: the key must be '<gold|ops>.<table>' and match its schema.")
        table = _ident(t["table"], f"{path}.table")
        if (schema, table.lower()) in taken:
            raise DataMapError(f"{path}: table '{table}' is already mapped from {taken[(schema, table.lower())]}.")
        taken[(schema, table.lower())] = key
        result[key] = {"schema": schema, "table": table, "logical": logical, "columns": _warehouse_columns(t["columns"], path)}
    return result


def _warehouse_columns(columns: Any, path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for logical, node in _keys(columns, f"{path}.columns", (), tuple(columns)).items():
        c_path = f"{path}.columns.{logical}"
        column = _ident(_keys(node, c_path, ("column", "type"))["column"], f"{c_path}.column")
        if column != logical:
            raise DataMapError(
                f"{c_path}: Warehouse column renaming is not implemented (R2.7 is open); "
                f"the column must be '{logical}', not '{column}'.")
        result[logical] = column
    return result


def _lakehouse(lake: Any) -> dict[str, Any]:
    section = _keys(lake, "lakehouse", ("database", "schema", "case_insensitive_columns", "naming", "transforms", "tables"))
    naming = _keys(section["naming"], "lakehouse.naming", ("table_prefix", "table_case"))
    if not PREFIX.match(str(naming["table_prefix"])):
        raise DataMapError("lakehouse.naming.table_prefix is not a plain identifier prefix.")
    _keys(section["transforms"], "lakehouse.transforms", ("worksite_location", "null_pay_date"))
    taken: dict[str, str] = {}
    for logical, node in _keys(section["tables"], "lakehouse.tables", (), tuple(section["tables"])).items():
        path = f"lakehouse.tables.{logical}"
        t = _keys(node, path, ("table", "dataset_attr", "columns"), ("tenant_field", "partition_by", "optional_reason"))
        name = _ident(t["table"], f"{path}.table")
        if name.lower() in taken:
            raise DataMapError(f"{path}: table '{name}' is already mapped from {taken[name.lower()]}.")
        taken[name.lower()] = logical
        _lakehouse_columns(t["columns"], path)
    return section


def _lakehouse_columns(columns: Any, path: str) -> None:
    taken: dict[str, str] = {}
    for field, node in _keys(columns, f"{path}.columns", (), tuple(columns)).items():
        c_path = f"{path}.columns.{field}"
        c = _keys(node, c_path, ("column", "type", "required", "engine"))
        column = _ident(c["column"], f"{c_path}.column")
        if column.lower() in taken:
            raise DataMapError(f"{c_path}: column '{column}' is already mapped from {taken[column.lower()]}.")
        taken[column.lower()] = field
        for flag in ("required", "engine"):
            if not isinstance(c[flag], bool):
                raise DataMapError(f"{c_path}.{flag} must be true or false.")


def parse(raw: bytes, source: str, reference: DataMap | None = None) -> DataMap:
    """Parse and validate; with a `reference`, also require exactly its logical entries."""
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except ValueError as exc:
        raise DataMapError(f"The data map is not valid JSON: {exc}") from None
    root = _keys(doc, "", ("version", "lakehouse", "warehouse"))
    if root["version"] != 1 or isinstance(root["version"], bool):
        raise DataMapError("version must be 1.")
    wh = _keys(root["warehouse"], "warehouse", ("database", "schemas", "tables"))
    schemas = _keys(wh["schemas"], "warehouse.schemas", ("gold", "ops"))
    gold, ops = _ident(schemas["gold"], "warehouse.schemas.gold"), _ident(schemas["ops"], "warehouse.schemas.ops")
    if gold.lower() == ops.lower():
        raise DataMapError("warehouse.schemas.gold and warehouse.schemas.ops must differ.")
    lake = _lakehouse(root["lakehouse"])
    data = DataMap(
        source=source, sha256=hashlib.sha256(raw).hexdigest(),
        source_database=_database_name(lake, "lakehouse"), warehouse_database=_database_name(wh, "warehouse"),
        source_schema=_ident(lake["schema"], "lakehouse.schema"), gold_schema=gold, ops_schema=ops,
        tables=_warehouse_tables(wh["tables"]), lakehouse=lake)
    if reference is not None:
        check_complete(reference, data)
    return data


def _same(path: str, expected: Any, actual: Any) -> None:
    for key in expected:
        if key not in actual:
            raise DataMapError(f"{path}.{key} is missing.")
    for key in actual:
        if key not in expected:
            raise DataMapError(f"{path}.{key} is not a known key.")


def check_complete(reference: DataMap, supplied: DataMap) -> None:
    """Fail naming the first logical entry the supplied map lacks or adds."""
    _same("warehouse.tables", reference.tables, supplied.tables)
    for key, table in reference.tables.items():
        _same(f"warehouse.tables.{key}.columns", table["columns"], supplied.tables[key]["columns"])
    ref_tables, got_tables = reference.lakehouse["tables"], supplied.lakehouse["tables"]
    _same("lakehouse.tables", ref_tables, got_tables)
    for logical, table in ref_tables.items():
        _same(f"lakehouse.tables.{logical}.columns", table["columns"], got_tables[logical]["columns"])
