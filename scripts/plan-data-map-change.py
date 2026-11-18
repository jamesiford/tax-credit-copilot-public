"""Print, never run, what an existing database would need to match a new data map.

    python scripts/plan-data-map-change.py --current current-map.json --new new-map.json

The application never renames or drops database objects. If your Warehouse already holds our
objects under the shipped (or an earlier) names and you now want different ones, this prints
READ-ONLY review SQL: a check for each object that exists under the current name, and the
`sp_rename` statements an operator could choose to run by hand. It refuses anything that
would drop or truncate, and never connects to a database.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from data_map import default_map  # noqa: E402
from data_map_load import parse  # noqa: E402

FORBIDDEN = ("DROP ", "TRUNCATE ", "DELETE ")


def load(path: Path):
    return parse(path.read_bytes(), "file", default_map())


def plan(current, new) -> list[str]:
    """Review SQL lines; each is a comment, a read-only SELECT, or a rename a human must choose to run."""
    lines = ["-- REVIEW ONLY. Nothing here has been run. Take a backup, stop writers, run by hand.", ""]
    schemas = {"gold": (current.gold_schema, new.gold_schema), "ops": (current.ops_schema, new.ops_schema)}
    for logical, (old, target) in schemas.items():
        if old.lower() != target.lower():
            lines += [f"-- schema {logical}: {old} -> {target}",
                      f"-- A schema cannot be renamed in place. Create '{target}', move each table with",
                      f"--   ALTER SCHEMA [{target}] TRANSFER [{old}].[<table>];  (one per table below)", ""]
    for key, table in new.tables.items():
        old_table, new_table = current.tables[key]["table"], table["table"]
        old_schema, new_schema = schemas[table["schema"]]
        if (old_schema.lower(), old_table.lower()) == (new_schema.lower(), new_table.lower()):
            continue
        lines.append(f"SELECT COUNT(*) AS exists_now FROM INFORMATION_SCHEMA.TABLES "
                     f"WHERE TABLE_SCHEMA = '{old_schema}' AND TABLE_NAME = '{old_table}';  -- {key}")
        if old_schema.lower() != new_schema.lower():
            lines.append(f"-- ALTER SCHEMA [{new_schema}] TRANSFER [{old_schema}].[{old_table}];")
        if old_table.lower() != new_table.lower():
            lines.append(f"-- EXEC sp_rename '{new_schema}.{old_table}', '{new_table}';")
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--current", type=Path, required=True)
    p.add_argument("--new", type=Path, required=True)
    args = p.parse_args(argv)
    lines = plan(load(args.current), load(args.new))
    emitted = [ln for ln in lines if not ln.lstrip().startswith("--")]
    if any(word in ln.upper() for ln in emitted for word in FORBIDDEN):
        print("refused: the plan would contain a destructive statement", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
