#!/usr/bin/env python
"""Build a sample lakehouse in the source mapping's shape, and reconcile it. [05]

    python scripts/fabric/build-sample-lakehouse.py --root DIR [--mapping-file F] [--source demo|scale] [--dry-run]
    python scripts/fabric/build-sample-lakehouse.py --fabric --yes [--mapping-file F]     (the configured Fabric lakehouse)

The shape (table names, column names and case, types, the `Payroll` partition by the tenant column) is whatever the source
mapping says: pass `--mapping-file` (or set SOURCE_MAPPING_FILE) to build in a customer's shape with no code change. The existing
sample data is mapped in; types are converted; missing optional columns are null.

- `--dry-run` writes NOTHING: it prints the plan (tables, physical names, columns, partitions, row counts) and the data-quality report.
- Re-running is idempotent: tables are overwritten, never appended.
- Reconciliation (local target): per table, rows and a checksum of the logical values before (the datasets) and after (read back
  from the lake); any difference exits 1.
- The app-owned lookups (`PayFrequency`, `EntityFiscalYearRules`) are NOT written unless `--with-lookups`, so absent-lookup
  behaviour can be tested end to end. Nothing here writes any personal identifier.
- `--fabric` writes to the lakehouse named by FABRIC_WORKSPACE / FABRIC_LAKEHOUSE over OneLake and refuses without `--yes`.

`--source scale` generates N accounts / M payroll rows with a realistic skew (see `scripts/generate-synthetic-source.py`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def _datasets(args: argparse.Namespace):
    if args.source == "scale":
        from data.source.scale import generate

        return generate(args.accounts, args.rows, args.seed)
    from data.source.synth import build_all_synthetic

    return build_all_synthetic()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="a local lakehouse root to write (contains Tables/)")
    parser.add_argument("--fabric", action="store_true", help="write to the configured Fabric lakehouse")
    parser.add_argument("--yes", action="store_true", help="confirm a Fabric write")
    parser.add_argument("--mapping-file", help="the source mapping (default: the shipped default)")
    parser.add_argument("--schema", default=None, help="schema folder under Tables/ (default: SOURCE_SCHEMA for Fabric, none locally)")
    parser.add_argument("--source", choices=("demo", "scale"), default="demo")
    parser.add_argument("--accounts", type=int, default=50)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--with-lookups", action="store_true", help="also write PayFrequency and EntityFiscalYearRules")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", help="write the report as JSON")
    return parser


def _plain(value):
    return json.loads(json.dumps(value, default=str))


def _write_fabric(datasets, args: argparse.Namespace, quality: dict) -> dict:
    from config import SOURCE_SCHEMA
    from data.source import build_lake
    from data.source.to_delta import write_datasets

    schema = SOURCE_SCHEMA if args.schema is None else args.schema
    counts = write_datasets(datasets, schema=schema, mode="overwrite", tables=build_lake.tables_to_write(args.with_lookups))
    return {"dry_run": False, "written_rows": counts, "quality": _plain(quality),
            "next": "verify with scripts/validate-source-schema.py and compare row counts over the SQL endpoint"}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if bool(args.root) == args.fabric:
        parser.error("name exactly one target: --root DIR or --fabric")
    if args.fabric and not (args.yes or args.dry_run):
        parser.error("--fabric writes to a shared lakehouse; add --yes (or --dry-run to see the plan)")
    if args.mapping_file:
        os.environ["SOURCE_MAPPING_FILE"] = args.mapping_file

    from data.source import build_lake

    datasets = _datasets(args)
    quality = build_lake.quality_report(datasets)
    if args.fabric and not args.dry_run:
        report, ok = _write_fabric(datasets, args, quality), True
    elif args.fabric:
        report, ok = {**build_lake.BuildReport(True, build_lake.plan_build(datasets, args.with_lookups)).as_dict(), "quality": _plain(quality)}, True
    else:
        built = build_lake.build_local(datasets, Path(args.root), schema=args.schema or "", include_lookups=args.with_lookups, dry_run=args.dry_run)
        report, ok = {**built.as_dict(), "quality": _plain(quality)}, args.dry_run or built.ok
    print(json.dumps(report, indent=2, default=str))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
