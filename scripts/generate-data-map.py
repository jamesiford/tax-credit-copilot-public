"""Generate the data map: the shipped complete file, or a draft from a customer's database.

    python scripts/generate-data-map.py --defaults [--out docs/data/data-map.json] [--check]
    python scripts/generate-data-map.py --from-database --lakehouse-conn "<odbc>" --warehouse-conn "<odbc>" --out my-map.json

`--defaults` builds the shipped file from the repository's Warehouse DDL and the Lakehouse
source mapping, so the file cannot drift from either. `--from-database` is read-only
(INFORMATION_SCHEMA only): it pairs each logical entry to a physical table or column by
case-insensitive EXACT name, and writes every unmatched entry with `"physical": null` and a
`_todo` note for a human to complete. It never guesses and never writes to a database.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_map_ddl import ROOT, read_warehouse_ddl  # noqa: E402

SHIPPED = ROOT / "docs" / "data" / "data-map.json"
LAKEHOUSE_DEFAULT = ROOT / "backend" / "data" / "source" / "mapping" / "default.json"
DOC = "Keys starting with an underscore are ignored by the loader and may be used for notes."


def _lakehouse(source: dict) -> dict:
    tables = {}
    for logical, t in source["tables"].items():
        entry = {"table": t["table"], "dataset_attr": t["dataset_attr"]}
        for optional in ("tenant_field", "partition_by", "optional_reason"):
            if optional in t:
                entry[optional] = t[optional]
        entry["columns"] = {
            name: {
                "column": f["column"],
                "type": f["type"],
                "required": f.get("required", True),
                "engine": f.get("engine", True),
            }
            for name, f in t["fields"].items()
        }
        tables[logical] = entry
    return {
        "database": {"logical": "source", "name": None},
        "schema": "tcc_source",
        "case_insensitive_columns": source.get("case_insensitive_columns", True),
        "naming": source["naming"],
        "transforms": source["transforms"],
        "tables": tables,
    }


def _warehouse() -> dict:
    tables = {}
    for key, columns in read_warehouse_ddl().items():
        schema, table = key.split(".")
        tables[key] = {
            "schema": schema,
            "table": table,
            "columns": {name: {"column": name, "type": ctype} for name, ctype in columns},
        }
    return {
        "database": {"logical": "warehouse", "name": None},
        "schemas": {"gold": "tcc_gold", "ops": "tcc_ops"},
        "tables": tables,
    }


def build_defaults() -> dict:
    source = json.loads(LAKEHOUSE_DEFAULT.read_text(encoding="utf-8"))
    return {"version": 1, "_doc": DOC, "lakehouse": _lakehouse(source), "warehouse": _warehouse()}


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _read_columns(conn_string: str, schema_filter: set[str]) -> dict[tuple[str, str], set[str]]:
    import pyodbc  # imported late: --defaults needs only the standard library

    found: dict[tuple[str, str], set[str]] = {}
    with pyodbc.connect(conn_string, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS")
        for schema, table, column in cursor.fetchall():
            if not schema_filter or schema.lower() in schema_filter:
                found.setdefault((schema.lower(), table.lower()), set()).add(column.lower())
    return found


def _pair_name(logical: str, present: set[str] | None, actual: dict[str, str] | None = None) -> str | None:
    return logical if present is not None and logical.lower() in present else None


def build_draft(lake_conn: str, wh_conn: str) -> dict:
    data = build_defaults()
    lake = data["lakehouse"]
    lake_cols = _read_columns(lake_conn, set())
    lake_schema = lake["schema"].lower()
    for logical, t in lake["tables"].items():
        present = lake_cols.get((lake_schema, t["table"].lower()))
        if present is None:
            t["table"] = None
            t["_todo"] = f"No table named {logical} in schema {lake['schema']}; set the physical table name."
        for name, c in t["columns"].items():
            if present is not None and c["column"].lower() in present:
                continue
            c["column"] = None
            c["_todo"] = f"No column named {name} found; set the physical column name or remove the mapping only if the field is optional."
    wh = data["warehouse"]
    wh_cols = _read_columns(wh_conn, {s.lower() for s in wh["schemas"].values()})
    for key, t in wh["tables"].items():
        present = wh_cols.get((wh["schemas"][t["schema"]].lower(), t["table"].lower()))
        if present is None:
            t["table"] = None
            t["_todo"] = f"No table named {key} found; set the physical table name."
        for name, c in t["columns"].items():
            if present is None or c["column"].lower() not in present:
                c["column"] = None
                c["_todo"] = f"No column named {name} found; set the physical column name."
    return data


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--defaults", action="store_true", help="write the shipped complete file")
    mode.add_argument("--from-database", action="store_true", help="read-only: write a complete draft map")
    p.add_argument("--out", type=Path, default=SHIPPED)
    p.add_argument("--check", action="store_true", help="with --defaults: fail if --out differs, write nothing")
    p.add_argument("--lakehouse-conn", help="ODBC connection string for the Lakehouse SQL endpoint")
    p.add_argument("--warehouse-conn", help="ODBC connection string for the Warehouse")
    args = p.parse_args(argv)
    if args.defaults:
        text = render(build_defaults())
        if args.check:
            current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
            if current != text:
                print(f"{args.out} differs from the generated defaults; run without --check", file=sys.stderr)
                return 1
            return 0
    else:
        if not (args.lakehouse_conn and args.warehouse_conn):
            p.error("--from-database needs --lakehouse-conn and --warehouse-conn")
        text = render(build_draft(args.lakehouse_conn, args.warehouse_conn))
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
