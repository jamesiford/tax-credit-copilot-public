"""Read the physical schema from the repo's own DDL and source definitions, for drift tests.

Parses the Warehouse bootstrap and every migration (CREATE TABLE and ALTER TABLE ... ADD),
and reads the lakehouse tables from `data/source/to_delta.TABLE_SPECS`. No database is
needed: the question is whether the semantic model agrees with what the repo says exists.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "docs" / "data" / "schema"

_CREATE = re.compile(r"CREATE\s+TABLE\s+(\w+\.\w+)\s*\((.*?)\n\)\s*;", re.IGNORECASE | re.DOTALL)
_ALTER_ADD = re.compile(r"ALTER\s+TABLE\s+(\w+\.\w+)\s+ADD\s+(\w+)\s+\w", re.IGNORECASE)
_NOT_COLUMNS = {"constraint", "primary", "unique", "foreign", "check", "index"}


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", sql)


def _split_top_level(body: str) -> list[str]:
    parts, depth, current = [], 0, []
    for char in body:
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def parse_ddl(sql: str) -> dict[str, list[str]]:
    """`schema.table` -> its column names, from CREATE TABLE and ALTER TABLE ... ADD."""
    clean = _strip_comments(sql)
    tables: dict[str, list[str]] = {}
    for name, body in _CREATE.findall(clean):
        columns = [p.split()[0] for p in _split_top_level(body) if p.split()[0].lower() not in _NOT_COLUMNS]
        tables[name] = columns
    for name, column in _ALTER_ADD.findall(clean):
        if column.lower() not in _NOT_COLUMNS:
            tables.setdefault(name, []).append(column)
    return tables


def warehouse_tables() -> dict[str, list[str]]:
    """Every Warehouse table the repo defines: the bootstrap, then each migration in order."""
    files = [SCHEMA_DIR / "tcc-schema.fabric.sql", *sorted((SCHEMA_DIR / "migrations").glob("*.sql"))]
    tables: dict[str, list[str]] = {}
    for path in files:
        for name, columns in parse_ddl(path.read_text(encoding="utf-8")).items():
            tables.setdefault(name, []).extend(c for c in columns if c not in tables.get(name, []))
    return tables


def source_tables() -> dict[str, list[str]]:
    """Lakehouse table -> its physical (PascalCase) columns, as written to Delta."""
    from data.source.to_delta import TABLE_SPECS, _pascal

    return {table: [_pascal(f) for f in spec] for table, (_attr, spec) in TABLE_SPECS.items()}
