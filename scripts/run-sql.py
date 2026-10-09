"""Run T-SQL against a GUARDED Fabric Warehouse target.

    python scripts/run-sql.py --target d27 --resolve
    python scripts/run-sql.py --target d27 --file docs/data/schema/tcc-schema.fabric.sql --section 9 --expect-empty
    python scripts/run-sql.py --target deployed --file some.sql

The target is resolved through the Fabric REST API and checked against the
allow-list BEFORE any connection is opened (see schema_admin.check_target). A
mismatch exits 3 and executes nothing.

Batches are split on `GO` lines. With `--section N` only that top-level section
of the file runs, split into one statement per `;`. `--expect-empty` fails
(exit 1) unless every result set of every statement has zero rows.

Exit codes: 0 ok · 1 a statement failed or returned rows under --expect-empty ·
2 usage · 3 target guard refused.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import sql_common as common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="'deployed' or a pinned name (e.g. d27)")
    parser.add_argument("--resolve", action="store_true", help="resolve and check the target; run nothing")
    parser.add_argument("--file", type=Path, help="SQL file to run")
    parser.add_argument("--section", help="run only this top-level section of the file (e.g. 9)")
    parser.add_argument("--expect-empty", action="store_true", help="every result set must have 0 rows")
    args = parser.parse_args(argv)

    common.load_env()
    from config import GOLD_SCHEMA, OPS_SCHEMA
    from infrastructure.persistence.schema_admin import (
        TargetMismatch,
        extract_section,
        rename_schemas,
        run_batches,
        split_batches,
        split_statements,
        statement_label,
    )

    if not args.resolve and not args.file:
        parser.error("--file is required unless --resolve is given")

    try:
        allowed, resolved, connection = common.guarded_connection(args.target, resolve_only=args.resolve)
    except TargetMismatch as exc:
        print(f"GUARD REFUSED: {exc}", file=sys.stderr)
        return common.EXIT_GUARD
    print(
        f"target   : {allowed.name}\n"
        f"workspace: {resolved.workspace_id}\n"
        f"item     : {resolved.item_id} ({resolved.display_name})\n"
        f"endpoint : {resolved.endpoint}\n"
        f"guard    : PASS"
    )
    if args.resolve:
        return common.EXIT_OK

    text = rename_schemas(args.file.read_text(encoding="utf-8"), gold=GOLD_SCHEMA, ops=OPS_SCHEMA)
    if args.section:
        batches = split_statements(extract_section(text, args.section))
    else:
        batches = split_batches(text)
    labels = [statement_label(b) for b in batches]
    try:
        results = run_batches(connection, batches, labels=labels, stop_on_error=not args.expect_empty)
    finally:
        connection.close()

    failed = False
    for result in results:
        status = "ok"
        if result.error:
            status, failed = f"ERROR {result.error}", True
        elif args.expect_empty and result.rows:
            status, failed = f"NOT EMPTY ({result.rows} rows: {result.result_sets[0][:3]})", True
        elif result.result_sets:
            status = f"ok ({result.rows} rows in {len(result.result_sets)} result set(s))"
        print(f"[{result.index:03d}] {result.label[:70]:<70} {status}")
    print(f"batches: {len(results)}/{len(batches)} run, {'FAILED' if failed else 'all ok'}")
    return common.EXIT_FAILED if failed or len(results) != len(batches) else common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
