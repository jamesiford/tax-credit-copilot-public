"""Render the shipped Warehouse DDL under the names in a data map.

Why text from the shipped files and not placeholders: `tcc_ops.schema_migration` records each
migration's SHA-256, and those hashes are of the shipped text. Leaving the files as they are
keeps every recorded hash valid; this renderer, the one place that rewrites finished SQL,
substitutes the customer's schema and table names. With the shipped map it is the identity,
byte for byte, which `tests/test_data_map_render.py` proves for every DDL file.
"""
from __future__ import annotations

import re

from data_map import default_map
from data_map_load import DataMap


def render(sql: str, target: DataMap) -> str:
    """Rewrite shipped `schema.table`, bare schema names and INFORMATION_SCHEMA pairs to `target`'s names."""
    ship = default_map()
    schemas = {ship.gold_schema: target.gold_schema, ship.ops_schema: target.ops_schema}
    tables = {
        (ship_entry["schema"], ship_entry["table"]): target.tables[key]["table"]
        for key, ship_entry in ship.tables.items()
    }
    logical_of = {ship.gold_schema: "gold", ship.ops_schema: "ops"}
    alternation = "|".join(re.escape(s) for s in schemas)
    pattern = re.compile(
        rf"(?P<pre>TABLE_SCHEMA\s*=\s*')(?P<ps>{alternation})(?P<mid>'\s+AND\s+TABLE_NAME\s*=\s*')(?P<pt>\w+)(?P<end>')"
        rf"|\b(?P<qs>{alternation})\.(?P<qt>[A-Za-z_]\w*)\b"
        rf"|\b(?P<bs>{alternation})\b"
    )

    def actual_table(schema: str, table: str) -> str:
        return tables.get((logical_of[schema], table), table)

    def swap(m: re.Match[str]) -> str:
        if m.group("ps"):
            schema = m.group("ps")
            return f"{m.group('pre')}{schemas[schema]}{m.group('mid')}{actual_table(schema, m.group('pt'))}{m.group('end')}"
        if m.group("qs"):
            return f"{schemas[m.group('qs')]}.{actual_table(m.group('qs'), m.group('qt'))}"
        return schemas[m.group("bs")]

    return pattern.sub(swap, sql)
