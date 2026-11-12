"""Create the Entra database users on an Azure SQL target, then grant them what they need. [09]

    python scripts/grant-sql.py --platform azure_sql --target deployed [--profile api|gateway] [--principal <name>] [--dry-run]

On the Fabric Warehouse, access comes from a Fabric workspace role and `grant-warehouse-sql.py` only
issues GRANTs. An Azure SQL database has no workspace: each identity must first exist as a database
user, created `FROM EXTERNAL PROVIDER` (Microsoft Entra). Users, groups and managed identities are all
created by display name. Entra authentication only: no SQL login and no password is created or accepted.

Per principal, in order:

1. `CREATE USER [<name>] FROM EXTERNAL PROVIDER`, only when `sys.database_principals` has no such name,
   so a re-run changes nothing.
2. The grants of the same profile `grant-warehouse-sql.py` uses (`api`: read/write on both schemas;
   `gateway`: INSERT and SELECT on the channel audit table, nothing else). The permission sets are
   imported from that script, so the two platforms cannot drift.

WHO RUNS IT: the server's Entra admin (the admin group in Terraform's `azure_sql` module) or a principal
that is allowed to create users from an external provider. The API's own managed identity cannot: it is
granted data access here and nothing more. The target is checked against the allow-list before any
connection is opened (see `sql_common.allowed_sql_target`).

Exit codes: 0 ok · 1 a statement failed · 2 usage · 3 target guard refused.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

import sql_common as common

_PROFILES = ("api", "gateway")


def _grants():
    """`grant-warehouse-sql.py` as a module: its file name has a hyphen, so it cannot be imported by name."""
    path = Path(__file__).with_name("grant-warehouse-sql.py")
    spec = importlib.util.spec_from_file_location("grant_warehouse_sql", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_user_statement(principal: str) -> str:
    """Idempotent user creation from Entra. The name was validated by the grant module; no quote can reach here."""
    _grants()._check_principal(principal)
    return (
        f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{principal}') "
        f"CREATE USER [{principal}] FROM EXTERNAL PROVIDER;"
    )


def statements_for(profile: str, principal: str, gold: str, ops: str) -> list[str]:
    """The user, then the profile's grants."""
    return [create_user_statement(principal), *_grants().statements_for(profile, principal, gold, ops)]


def _principal(parser: argparse.ArgumentParser, profile: str, given: str | None) -> str:
    env_name = "GATEWAY_IDENTITY_NAME" if profile == "gateway" else "API_IDENTITY_NAME"
    principal = given or os.getenv(env_name, "")
    if not principal:
        parser.error(f"--principal (or {env_name}) is required")
    return principal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=("azure_sql",), help="the Fabric Warehouse uses grant-warehouse-sql.py")
    parser.add_argument("--target", required=True)
    parser.add_argument("--profile", choices=_PROFILES, default="api")
    parser.add_argument("--principal", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    common.load_env()
    from config import GOLD_SCHEMA, OPS_SCHEMA
    from infrastructure.persistence.fabric_warehouse import WarehouseNotConfigured
    from infrastructure.persistence.schema_admin import TargetMismatch, run_batches

    statements = statements_for(args.profile, _principal(parser, args.profile, args.principal), GOLD_SCHEMA, OPS_SCHEMA)
    if args.dry_run:
        print("\n".join(statements))
        return common.EXIT_OK
    try:
        _, _, connection = common.guarded_sql_connection(args.target)
    except TargetMismatch as exc:
        print(f"GUARD REFUSED: {exc}", file=sys.stderr)
        return common.EXIT_GUARD
    except WarehouseNotConfigured as exc:
        print(f"NOT CONFIGURED: {exc}", file=sys.stderr)
        return common.EXIT_USAGE
    try:
        results = run_batches(connection, statements)
    finally:
        connection.close()
    for result in results:
        print(f"  {'ERROR ' + result.error if result.error else 'ok'}  {statements[result.index - 1]}")
    return common.EXIT_FAILED if any(r.error for r in results) or len(results) != len(statements) else common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
