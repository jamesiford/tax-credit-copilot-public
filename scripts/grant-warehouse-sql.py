"""Grant an identity access to tcc_gold / tcc_ops. [FAB-2, FAB-3]

    python scripts/grant-warehouse-sql.py --target deployed [--profile api|gateway] [--principal <name>] [--dry-run]

Fabric workspace roles are Fabric's business (Terraform's `manage_fabric_access`
or the customer's Fabric admin); schema permissions are T-SQL. GRANT is
idempotent, so a re-run changes nothing.

Three profiles:

- `api` (default) — read/write on both schemas, for the API identity (Terraform
  output API_IDENTITY_NAME). The schema-level grant already covers any table a
  migration adds.
- `gateway` — the channel gateway's identity (GATEWAY_IDENTITY_NAME). Object-level
  only: INSERT and SELECT on `tcc_ops.channel_audit`, and nothing else. The gateway
  writes the audit trail; it reads and changes business data through the API.
- `lakehouse` — READ ONLY, on the lakehouse SQL analytics endpoint, for the API identity: SELECT
  on each source table the governed data query reads (the semantic model's `lakehouse`
  datasets), at object level. No schema grant, no INSERT/UPDATE/DELETE, no db_owner. It never
  accepts the gateway identity: the gateway never touches data directly. postprovision runs it
  only when TCC_DATA_QUERY_SOURCE_ENABLED=true.

Exit codes: 0 ok · 1 a grant failed · 2 usage (or a lakehouse endpoint not configured) · 3 target guard refused.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import sql_common as common

_PERMISSIONS = "SELECT, INSERT, UPDATE, DELETE"
_GATEWAY_PERMISSIONS = "INSERT, SELECT"
GATEWAY_OBJECTS = ("channel_audit",)
LAKEHOUSE_PERMISSIONS = "SELECT"
PROFILES = ("api", "gateway", "lakehouse")


def _check_principal(principal: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9 ._@-]{1,128}", principal):
        raise ValueError(f"refusing an unusual principal name: {principal!r}")


def _check_identifier(kind: str, name: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
        raise ValueError(f"refusing {kind} name {name!r}")


def grant_statements(principal: str, schemas: list[str]) -> list[str]:
    _check_principal(principal)
    for schema in schemas:
        _check_identifier("schema", schema)
    return [f"GRANT {_PERMISSIONS} ON SCHEMA::{schema} TO [{principal}];" for schema in schemas]


def gateway_grant_statements(principal: str, ops_schema: str, objects: tuple[str, ...] = GATEWAY_OBJECTS) -> list[str]:
    """INSERT and SELECT on the named tables only: no schema grant, no UPDATE, no DELETE."""
    _check_principal(principal)
    _check_identifier("schema", ops_schema)
    for name in objects:
        _check_identifier("object", name)
    return [f"GRANT {_GATEWAY_PERMISSIONS} ON OBJECT::{ops_schema}.{name} TO [{principal}];" for name in objects]


def lakehouse_source_tables() -> tuple[str, ...]:
    """The source tables the data query reads, from the semantic model so the two cannot drift."""
    from application.data.semantic_model import Source, default_model

    return tuple(sorted(d.table for d in default_model().datasets if d.source is Source.LAKEHOUSE))


def lakehouse_grant_statements(principal: str, source_schema: str, tables: tuple[str, ...]) -> list[str]:
    """SELECT on the named source tables only: read-only, object level, nothing else."""
    _check_principal(principal)
    _check_identifier("schema", source_schema)
    for name in tables:
        _check_identifier("object", name)
    return [f"GRANT {LAKEHOUSE_PERMISSIONS} ON OBJECT::{source_schema}.{name} TO [{principal}];" for name in tables]


def statements_for(
    profile: str,
    principal: str,
    gold: str,
    ops: str,
    source: str | None = None,
    source_tables: tuple[str, ...] | None = None,
) -> list[str]:
    if profile == "gateway":
        return gateway_grant_statements(principal, ops)
    if profile == "lakehouse":
        return lakehouse_grant_statements(
            principal, source or "tcc_source", source_tables if source_tables is not None else lakehouse_source_tables()
        )
    return grant_statements(principal, [gold, ops])


def _principal(parser: argparse.ArgumentParser, profile: str, given: str | None) -> str:
    """The identity to grant to; the lakehouse profile refuses the gateway's, which never reads data."""
    env_name = "GATEWAY_IDENTITY_NAME" if profile == "gateway" else "API_IDENTITY_NAME"
    principal = given or os.getenv(env_name, "")
    if not principal:
        parser.error("--principal (or API_IDENTITY_NAME / GATEWAY_IDENTITY_NAME) is required")
    gateway = os.getenv("GATEWAY_IDENTITY_NAME", "")
    if profile == "lakehouse" and gateway and principal == gateway:
        parser.error("the lakehouse profile never grants the gateway identity: the gateway never touches data directly")
    return principal


def _connect(profile: str, target: str):
    """A guarded connection to the endpoint the profile's grants are issued on."""
    if profile == "lakehouse":
        return common.guarded_lakehouse_connection(target)
    return common.guarded_connection(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True)
    parser.add_argument("--profile", choices=PROFILES, default="api")
    parser.add_argument("--principal", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    common.load_env()
    from config import GOLD_SCHEMA, OPS_SCHEMA, SOURCE_SCHEMA
    from infrastructure.persistence.fabric_warehouse import WarehouseNotConfigured
    from infrastructure.persistence.schema_admin import TargetMismatch, run_batches

    principal = _principal(parser, args.profile, args.principal)
    statements = statements_for(args.profile, principal, GOLD_SCHEMA, OPS_SCHEMA, SOURCE_SCHEMA)
    if args.dry_run:
        print("\n".join(statements))
        return common.EXIT_OK

    try:
        allowed, resolved, connection = _connect(args.profile, args.target)
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
