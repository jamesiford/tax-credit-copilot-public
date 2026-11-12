#!/usr/bin/env python
"""Build or refresh the Silver table: engine-shaped payroll partitioned by account. [08.3, 08.4]

    python scripts/fabric/build-silver.py --root DIR [--schema S] [--accounts 1,2,3] [--force] [--dry-run]
    python scripts/fabric/build-silver.py --fabric --yes [--accounts ...]        (the configured Fabric lakehouse)

Reads each account through the app's own reader (so Silver is exactly what the raw path would give the engine), writes one
partition per account to `tcc_silver_pay_period` beside the Payroll table, and records the source Payroll Delta version on every row.
A re-run builds only the accounts whose recorded version is not the current one: an unchanged lake is a no-op. `--force` rebuilds.
The app reads Silver when `SOURCE_SILVER=auto` (falling back to raw for an account with no partition) or `require`; the default is
`off`, so building Silver changes nothing until it is switched on. Silver is unaware of the app-owned lookups: the pay-code
category is applied at read time. A Fabric run is a Spark-scale job in practice; this script is the reference implementation of its
logic and has been run on local lakes only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="a local lakehouse root (contains Tables/)")
    parser.add_argument("--fabric", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--schema", default=None)
    parser.add_argument("--mapping-file")
    parser.add_argument("--accounts", help="comma-separated account ids (default: every account)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.root) == args.fabric:
        parser.error("name exactly one target: --root DIR or --fabric")
    if args.fabric and not (args.yes or args.dry_run):
        parser.error("--fabric writes to a shared lakehouse; add --yes (or --dry-run)")
    if args.mapping_file:
        os.environ["SOURCE_MAPPING_FILE"] = args.mapping_file

    from data.source import from_fabric, onelake
    from data.source.mapping import column
    from data.source.silver_build import build_silver

    if args.root:
        root, schema = Path(args.root), args.schema or ""

        def local(table, *, workspace, lakehouse, schema):  # a local lake, no credential
            folder = root / "Tables" / schema if schema else root / "Tables"
            return str(folder / onelake.physical_table(table))

        from_fabric.table_uri = local
        from_fabric.FabricLakehouseReader._storage_options = lambda self: {}
        reader = from_fabric.FabricLakehouseReader(workspace="local", lakehouse="local", schema=schema)
    else:
        from config import SOURCE_SCHEMA

        reader = from_fabric.FabricLakehouseReader(schema=SOURCE_SCHEMA if args.schema is None else args.schema)
    accounts = [int(a) for a in args.accounts.split(",")] if args.accounts else None
    report = build_silver(reader, reader._silver_uri(), column("Payroll", "account_id"), accounts=accounts, force=args.force,
                          storage_options=None if args.root else reader._storage_options(), dry_run=args.dry_run)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
