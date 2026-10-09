"""Load the four tenants into the Fabric Lakehouse in the partner's source shape.

    cd backend
    python -m data.source.load_fabric              # write all four tenants
    python -m data.source.load_fabric --dry-run    # build and report, write nothing
    python -m data.source.load_fabric --synthetic-only
    python -m data.source.load_fabric --accounts 2001   # rewrite ONE synthetic tenant

A plain run OVERWRITES each table with whatever it built, so `--synthetic-only`
drops the reference client from every table it writes. `--accounts` is the safe
way to reshape a synthetic client: it replaces only that tenant's rows in
`Payroll` (by `AccountId`) and `Employment` (by the tenant's employee-id block),
and leaves every other tenant, including Candle Bottle, untouched. Add
`--tables Account` to rewrite only those tenants' Account rows (WI-20).

Reads `FABRIC_WORKSPACE` and `FABRIC_LAKEHOUSE` from the environment (they are
already set in the azd env). Auth is `DefaultAzureCredential`, so `az login` or
a managed identity — no keys.

Writes under the configured source schema (`SOURCE_SCHEMA`, default
`tcc_source`), leaving the existing `dbo` demo tables alone.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow `python data/source/load_fabric.py` as well as `python -m data.source.load_fabric`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import SOURCE_SCHEMA
from data.source.from_reference import build_reference_source_dataset
from data.source.synth import build_all_synthetic
from data.source.to_bcs import source_to_bcs_rows, projection_controls
from data.source.to_delta import TABLE_SPECS, write_datasets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="build and report; write nothing to OneLake")
    parser.add_argument("--synthetic-only", action="store_true",
                        help="skip the reference client (confidential payroll)")
    parser.add_argument("--accounts", nargs="+", type=int, metavar="ID",
                        help="rewrite only these synthetic tenants' Payroll and "
                             "Employment rows; every other tenant is left alone")
    parser.add_argument("--schema", default=SOURCE_SCHEMA,
                        help=f"lakehouse schema to write under (default: {SOURCE_SCHEMA})")
    parser.add_argument("--tables", nargs="+", metavar="TABLE",
                        help="write only these tables (default: all)")
    parser.add_argument("--workspace", default=os.getenv("FABRIC_WORKSPACE"))
    parser.add_argument("--lakehouse", default=os.getenv("FABRIC_LAKEHOUSE"))
    args = parser.parse_args()

    datasets = []
    predicates = None
    if args.accounts:
        from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset

        by_id = {spec.account_id: spec for spec in SYNTHETIC_CLIENTS}
        unknown = [a for a in args.accounts if a not in by_id]
        if unknown:
            print(f"not a synthetic account: {unknown}. The reference client is never "
                  "rewritten this way.", file=sys.stderr)
            return 2
        datasets = [build_synthetic_dataset(by_id[a]) for a in args.accounts]
        ids = ", ".join(str(a) for a in args.accounts)
        # Synthetic employee ids are `account_id * 100_000 + n` (synth.py), so a
        # tenant's Employment rows are one contiguous block.
        blocks = " OR ".join(
            f"(EmployeeId >= {a * 100_000} AND EmployeeId < {(a + 1) * 100_000})"
            for a in args.accounts
        )
        predicates = {
            "Payroll": f"AccountId IN ({ids})",
            "Employment": blocks,
            "Account": f"AccountId IN ({ids})",
            # Opt-in, like Account: a location's open date is reshaped only by
            # a story that opens a site late (GA-016, 30 Sep).
            "Location": f"AccountId IN ({ids})",
        }
        if args.tables and set(args.tables) - set(predicates):
            print(f"--accounts writes only {sorted(predicates)}", file=sys.stderr)
            return 2
        # Account is opt-in: a metadata change should not rewrite payroll, and a
        # payroll reshape should not have to rewrite the book.
        args.tables = args.tables or ["Employment", "Payroll"]
    else:
        if not args.synthetic_only:
            try:
                datasets.append(build_reference_source_dataset())
            except FileNotFoundError as exc:
                print(f"reference dataset unavailable, skipping: {exc}")
        datasets.extend(build_all_synthetic())

    print(f"{'client':30} {'account':>8} {'payroll':>10} {'employees':>10} {'sites':>6}")
    print("-" * 70)
    total = 0
    for ds in datasets:
        rows = source_to_bcs_rows(ds)
        c = projection_controls(ds, rows)
        total += c["payroll_rows_in"]
        print(f"{ds.account.name:30} {ds.account.account_id:>8} "
              f"{c['payroll_rows_in']:>10,} {c['distinct_employees']:>10,} "
              f"{c['distinct_worksites']:>6}")
    print("-" * 70)
    print(f"{'TOTAL':30} {'':>8} {total:>10,}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    if not args.workspace or not args.lakehouse:
        print("\nFABRIC_WORKSPACE and FABRIC_LAKEHOUSE must be set (or passed).",
              file=sys.stderr)
        return 2

    selected = args.tables or list(TABLE_SPECS)
    print(f"\nwriting {len(selected)} tables to "
          f"{args.lakehouse}.Lakehouse/Tables/{args.schema}/ ...")
    written = write_datasets(
        datasets,
        workspace=args.workspace,
        lakehouse=args.lakehouse,
        schema=args.schema,
        tables=selected,
        predicates=predicates,
    )
    for table, n in written.items():
        print(f"  {table:26} {n:>10,}")
    print(f"\ndone: {sum(written.values()):,} rows across {len(written)} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
