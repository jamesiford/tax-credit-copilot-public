"""Check that the operational store (claims, engagements, findings) is usable. Operator tool.

    python scripts/check-operational-store.py

Connects the way the app does (the `WAREHOUSE_*` settings and the same identity), then verifies in
order: the server answers, `tcc_ops.schema_migration` exists, the claim tables exist, every migration
in `docs/data/schema/migrations/` is applied, and the identity can read and write the claim table.
Prints the first problem with its remedy and any warnings (a placeholder host, SQLite claims while a
warehouse is configured). Exit code 0 when no problem was found, 1 otherwise. Changes nothing.
"""
from __future__ import annotations

import sys

import sql_common as common


def main() -> int:
    common.load_env()
    from application.store_readiness import check_operational_store
    from infrastructure.persistence.schema_admin import discover_migrations
    import bootstrap.wiring  # noqa: F401 - binds the store probe

    report = check_operational_store(discover_migrations(common.MIGRATIONS_DIR))
    for finding in report["problems"]:
        print(f"PROBLEM  {finding['message']}\n         remedy: {finding['remedy']}")
    for finding in report["warnings"]:
        print(f"warning  {finding['message']}\n         remedy: {finding['remedy']}")
    if not report["problems"]:
        print("ok: no problem found with the operational store.")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
