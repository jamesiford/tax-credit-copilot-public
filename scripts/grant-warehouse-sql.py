"""Grant the API identity read/write on tcc_gold and tcc_ops. [FAB-2, FAB-3]

    python scripts/grant-warehouse-sql.py --target deployed [--principal <name>] [--dry-run]

Fabric workspace roles are Fabric's business (Terraform's `manage_fabric_access`
or the customer's Fabric admin); schema permissions are T-SQL. The principal is
the API identity's display name (Terraform output API_IDENTITY_NAME). GRANT is
idempotent, so a re-run changes nothing.

Exit codes: 0 ok · 1 a grant failed · 2 usage · 3 target guard refused.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import sql_common as common

_PERMISSIONS = "SELECT, INSERT, UPDATE, DELETE"


def grant_statements(principal: str, schemas: list[str]) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9 ._@-]{1,128}", principal):
        raise ValueError(f"refusing an unusual principal name: {principal!r}")
    for schema in schemas:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", schema):
            raise ValueError(f"refusing schema name {schema!r}")
    return [f"GRANT {_PERMISSIONS} ON SCHEMA::{schema} TO [{principal}];" for schema in schemas]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True)
    parser.add_argument("--principal", default=os.getenv("API_IDENTITY_NAME", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    common.load_env()
    from config import GOLD_SCHEMA, OPS_SCHEMA
    from infrastructure.persistence.schema_admin import TargetMismatch, run_batches

    if not args.principal:
        parser.error("--principal (or API_IDENTITY_NAME) is required")
    statements = grant_statements(args.principal, [GOLD_SCHEMA, OPS_SCHEMA])
    if args.dry_run:
        print("\n".join(statements))
        return common.EXIT_OK

    try:
        allowed, resolved, connection = common.guarded_connection(args.target)
    except TargetMismatch as exc:
        print(f"GUARD REFUSED: {exc}", file=sys.stderr)
        return common.EXIT_GUARD
    try:
        results = run_batches(connection, statements)
    finally:
        connection.close()
    for result in results:
        print(f"  {'ERROR ' + result.error if result.error else 'ok'}  {statements[result.index - 1]}")
    return common.EXIT_FAILED if any(r.error for r in results) or len(results) != len(statements) else common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
