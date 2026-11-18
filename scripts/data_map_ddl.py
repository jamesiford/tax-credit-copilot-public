"""Read the repository's Warehouse DDL into {schema.table: [(column, type), ...]}.

Why this exists: the shipped data map must list every Warehouse table and column the
DDL creates, in DDL order, and a test must prove it lists nothing else. The DDL is the
single source of that inventory, so the parser lives here and is shared by the
generator and the tests.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DDL_FILES = [
    ROOT / "docs" / "data" / "schema" / "tcc-schema.fabric.sql",
    *sorted((ROOT / "docs" / "data" / "schema" / "migrations").glob("0*.sql")),
    ROOT / "dotnet" / "deploy" / "sql" / "0100_dotnet_operational_objects.sql",
]

_CREATE = re.compile(r"CREATE\s+TABLE\s+(tcc_(?:gold|ops))\.(\w+)\s*\(", re.I)
_ADD_COLUMN = re.compile(r"ALTER\s+TABLE\s+(tcc_(?:gold|ops))\.(\w+)\s+ADD\s+(?!CONSTRAINT\b)(\w+)\s+([A-Za-z0-9_]+(?:\s*\([^)]*\))?)", re.I)
_CONSTRAINT_START = ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK")


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"--[^\n]*", "", text)


def _split_top_level(body: str) -> list[str]:
    parts, depth, current = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _table_body(text: str, start: int) -> str:
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i]
    raise ValueError("unbalanced CREATE TABLE")


def _column(definition: str) -> tuple[str, str] | None:
    name, _, rest = definition.partition(" ")
    if name.upper() in _CONSTRAINT_START:
        return None
    match = re.match(r"\s*([A-Za-z0-9_]+(?:\s*\([^)]*\))?)", rest)
    return name, re.sub(r"\s+", "", match.group(1)).upper() if match else ""


def read_warehouse_ddl() -> "OrderedDict[str, list[tuple[str, str]]]":
    tables: "OrderedDict[str, list[tuple[str, str]]]" = OrderedDict()
    for path in DDL_FILES:
        text = _strip_comments(path.read_text(encoding="utf-8"))
        for match in _CREATE.finditer(text):
            key = f"{match.group(1)[4:]}.{match.group(2)}"
            if key in tables:
                continue
            columns = [c for c in map(_column, _split_top_level(_table_body(text, match.end()))) if c]
            tables[key] = columns
        for match in _ADD_COLUMN.finditer(text):
            key = f"{match.group(1)[4:]}.{match.group(2)}"
            column = (match.group(3), re.sub(r"\s+", "", match.group(4)).upper())
            if key in tables and column[0] not in [c[0] for c in tables[key]]:
                tables[key].append(column)
    return tables
