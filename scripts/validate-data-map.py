"""Validate a data map file: JSON Schema, the loader's rules, and (optionally) a live database.

    python scripts/validate-data-map.py my-map.json
    python scripts/validate-data-map.py my-map.json --check-database \
        --lakehouse-conn "<odbc>" --warehouse-conn "<odbc>"

Exit 0: valid. Exit 1: invalid, with every problem printed. `--check-database` is read-only
(INFORMATION_SCHEMA only) and prints EVERY table and column the map names that the database
does not hold, not just the first.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from data_map import default_map  # noqa: E402
from data_map_load import DataMapError, parse  # noqa: E402

SCHEMA = ROOT / "docs" / "data" / "data-map.schema.json"


def schema_problems(doc: object) -> list[str]:
    """Every JSON Schema violation, each with its path."""
    import jsonschema

    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message[:160]}" for e in validator.iter_errors(doc)]


def database_problems(data, lake_conn: str, wh_conn: str) -> list[str]:
    """Every mapped table or column the live databases do not hold (case-insensitive exact names)."""
    spec = importlib.util.spec_from_file_location("generate_data_map", ROOT / "scripts" / "generate-data-map.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    problems: list[str] = []
    lake = gen._read_columns(lake_conn, set())
    section = data.lakehouse
    for logical, table in section["tables"].items():
        present = lake.get((section["schema"].lower(), table["table"].lower()))
        if present is None:
            problems.append(f"lakehouse.tables.{logical}: no table {section['schema']}.{table['table']}")
            continue
        problems += [f"lakehouse.tables.{logical}.columns.{f}: no column {c['column']}"
                     for f, c in table["columns"].items() if c["column"].lower() not in present and c["required"]]
    wh = gen._read_columns(wh_conn, {data.gold_schema.lower(), data.ops_schema.lower()})
    for key, table in data.tables.items():
        schema = (data.gold_schema if table["schema"] == "gold" else data.ops_schema).lower()
        present = wh.get((schema, table["table"].lower()))
        if present is None:
            problems.append(f"warehouse.tables.{key}: no table {schema}.{table['table']}")
            continue
        problems += [f"warehouse.tables.{key}.columns.{c}: no column {a}"
                     for c, a in table["columns"].items() if a.lower() not in present]
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path)
    p.add_argument("--check-database", action="store_true")
    p.add_argument("--lakehouse-conn")
    p.add_argument("--warehouse-conn")
    args = p.parse_args(argv)
    raw = args.file.read_bytes()
    problems = schema_problems(json.loads(raw.decode("utf-8-sig")))
    data = None
    try:
        data = parse(raw, "file", default_map())
    except DataMapError as exc:
        problems.append(f"loader: {exc}")
    if args.check_database and data is not None:
        if not (args.lakehouse_conn and args.warehouse_conn):
            p.error("--check-database needs --lakehouse-conn and --warehouse-conn")
        problems += database_problems(data, args.lakehouse_conn, args.warehouse_conn)
    for line in problems:
        print(line)
    print(f"{args.file}: {'INVALID, ' + str(len(problems)) + ' problem(s)' if problems else 'valid'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
