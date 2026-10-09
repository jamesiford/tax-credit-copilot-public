"""Apply schema migrations to a GUARDED Fabric Warehouse target. [D22]

    python scripts/apply-migrations.py --target deployed
    python scripts/apply-migrations.py --target deployed --bootstrap      # postprovision, create_fabric only
    python scripts/apply-migrations.py --target d27 --bootstrap           # A06, once

Without `<ops>.schema_migration` the Warehouse has never been bootstrapped, and
this REFUSES unless `--bootstrap` is given AND the target is approved for it (a
pinned target with bootstrap_approved, or `deployed` with TCC_FABRIC_CREATED=true).
The bootstrap is DDL v2.0, which is destructive; it records version 0000.

With the table present, `--bootstrap` is ignored (logged) — the bootstrap never
re-runs on a Warehouse that has one — and every migration in
docs/data/schema/migrations/ whose version is not recorded is applied in order
and recorded. A re-run applies nothing.

Exit codes: 0 ok · 1 a migration failed or the state is unsafe · 2 usage ·
3 target guard refused.
"""
from __future__ import annotations

import argparse
import sys

import sql_common as common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="'deployed' or a pinned name (e.g. d27)")
    parser.add_argument("--bootstrap", action="store_true", help="allow the destructive bootstrap on an unbootstrapped, approved target")
    parser.add_argument("--dry-run", action="store_true", help="report what would run; change nothing")
    args = parser.parse_args(argv)

    common.load_env()
    from config import GOLD_SCHEMA, OPS_SCHEMA
    from infrastructure.persistence.schema_admin import (
        MigrationError,
        TargetMismatch,
        applied_migrations,
        apply_migration,
        bootstrap_sql,
        discover_migrations,
        pending_migrations,
        rename_schemas,
        run_batches,
        split_batches,
    )

    try:
        allowed, resolved, connection = common.guarded_connection(args.target)
    except TargetMismatch as exc:
        print(f"GUARD REFUSED: {exc}", file=sys.stderr)
        return common.EXIT_GUARD
    print(f"target {allowed.name}: {resolved.display_name} @ {resolved.endpoint} (guard PASS)")

    try:
        available = discover_migrations(common.MIGRATIONS_DIR)
        applied = applied_migrations(connection, OPS_SCHEMA)

        if applied is None:
            if not args.bootstrap:
                print(
                    f"REFUSED: {OPS_SCHEMA}.schema_migration does not exist, so this Warehouse has "
                    "never been bootstrapped. Re-run with --bootstrap on an approved target.",
                    file=sys.stderr,
                )
                return common.EXIT_FAILED
            if not allowed.bootstrap_approved:
                print(
                    f"REFUSED: target '{allowed.name}' is not approved for the destructive bootstrap "
                    "(pinned bootstrap_approved, or deployed with TCC_FABRIC_CREATED=true).",
                    file=sys.stderr,
                )
                return common.EXIT_FAILED
            ddl = rename_schemas(common.BOOTSTRAP_DDL.read_text(encoding="utf-8"), gold=GOLD_SCHEMA, ops=OPS_SCHEMA)
            batches = split_batches(bootstrap_sql(ddl))
            print(f"bootstrap: {len(batches)} batches from {common.BOOTSTRAP_DDL.name}")
            if args.dry_run:
                print("dry run: bootstrap NOT executed")
                return common.EXIT_OK
            results = run_batches(connection, batches)
            for r in results:
                print(f"  [{r.index:03d}] {'ERROR ' + r.error if r.error else 'ok'}  {r.label[:70]}")
            if any(r.error for r in results) or len(results) != len(batches):
                print("bootstrap FAILED", file=sys.stderr)
                return common.EXIT_FAILED
            applied = applied_migrations(connection, OPS_SCHEMA) or {}
            print(f"bootstrap applied; recorded versions: {sorted(applied)}")
        elif args.bootstrap:
            print(f"bootstrap skipped: {OPS_SCHEMA}.schema_migration already exists (D22)")

        todo = pending_migrations(available, applied)
        print(f"recorded: {sorted(applied)}  available: {[m.version for m in available]}  pending: {len(todo)}")
        for migration in todo:
            if args.dry_run:
                print(f"  would apply {migration.version}_{migration.name}")
                continue
            apply_migration(connection, migration, OPS_SCHEMA)
            print(f"  applied {migration.version}_{migration.name} ({migration.sha256[:12]})")
        return common.EXIT_OK
    except MigrationError as exc:
        print(f"MIGRATION ERROR: {exc}", file=sys.stderr)
        return common.EXIT_FAILED
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
