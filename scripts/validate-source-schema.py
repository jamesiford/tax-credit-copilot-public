#!/usr/bin/env python
"""Compare the source mapping with the lake, and print a precise report. [06.4]

    python scripts/validate-source-schema.py                      # the configured lakehouse (needs FABRIC_* set)
    python scripts/validate-source-schema.py --root DIR [--schema S]   # a lakehouse laid out on local disk
    python scripts/validate-source-schema.py --print-effective    # the mapping in force, no lake needed
    python scripts/validate-source-schema.py --json

Exit 0 when the engine can read the source (warnings are printed); 1 when a required table or column is
absent or cannot be read as mapped; 2 when the lake or the mapping cannot be opened at all. Only each table's
schema is read, never its rows. The mapping in force is the shipped default, or the file `SOURCE_MAPPING_FILE`
names layered over it; `SOURCE_TABLE_PREFIX`, `SOURCE_TABLE_CASE` and `SOURCE_TABLE_MAP` still override table names.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="a local lakehouse root (contains Tables/)")
    parser.add_argument("--schema", default="", help="schema folder under Tables/ for --root (empty: none)")
    parser.add_argument("--print-effective", action="store_true", help="print the effective mapping and exit")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    from data.source import mapping
    from data.source.mapping import validate
    from data.source.mapping.local import local_schemas

    try:
        if args.print_effective:
            print(json.dumps(mapping.describe(), indent=2))
            return 0
        from application.source_validation import validate_lake

        report = validate_lake(local_schemas(args.root, args.schema)) if args.root else validate_lake()
    except Exception as exc:  # noqa: BLE001 - the operator needs the reason, not a trace
        print(f"cannot check the source schema: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    from data.lookups import lookup_status

    present = {"entity_fiscal_year_rules": any(t.logical == "EntityFiscalYearRules" and t.present for t in report.tables)}
    lookups = lookup_status(present)
    if args.json:
        print(json.dumps({**report.summary(), "lookups": lookups}, indent=2))
    else:
        print(validate.render(report))
        print("\napp-owned lookups:")
        for row in lookups:
            print(f"  {row['lookup']:<26} {row['status']:<28} {row['affects']}" + (f"  IF MISSING: {row['if_missing']}" if row.get('if_missing') else ""))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
