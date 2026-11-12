"""The operational-store readiness probe, over the Warehouse connection. [03.7]

Checks, in order and stopping at the first that fails to establish the next: the server answers,
`tcc_ops.schema_migration` exists, the claim tables exist, the migrations on disk are all applied,
and the identity can read (and, where the engine can say so, write) the claim table. Each finding
names the remedy. Local stores (`sqlite`, `memory`) create their own schema, so there is nothing to
verify for them beyond settings.
"""
from __future__ import annotations

import logging
from typing import Any

from application.deployment import store_choice
from application.errors import as_dependency_failure
from application.store_readiness import Finding
from config import OPS_SCHEMA, get_settings

log = logging.getLogger(__name__)

_CLAIM_TABLES = ("program_claim", "program_engagement")

#: What to do on Azure SQL, where access is a database user rather than a Fabric workspace role.
_AZURE_REMEDIES = {
    "config": "Set WAREHOUSE_SERVER (the server FQDN) and WAREHOUSE_DATABASE, with WAREHOUSE_PLATFORM=azure_sql.",
    "bootstrap": (
        "Run `python scripts/apply-migrations.py --target deployed --bootstrap` "
        "(TCC_SQL_CREATED=true on a database Terraform just created)."
    ),
    "migrate": "Run `python scripts/apply-migrations.py --target deployed`.",
    "grants": (
        "Create the identity as a database user and grant it: `python scripts/grant-sql.py --platform azure_sql "
        "--target deployed --profile api` (run by the server's Entra admin)."
    ),
    "unreachable": (
        " Check the server firewall rule or private endpoint, and that the identity exists as a database user "
        "(CREATE USER ... FROM EXTERNAL PROVIDER)."
    ),
}


def _azure() -> bool:
    """Whether the operational store is an Azure SQL Database, whose remedies differ from Fabric's."""
    return get_settings().platform.is_azure_sql


class OperationalStoreProbe:
    """Verifies the Warehouse operational store; a local store needs no verification."""

    def __init__(self, connection: Any = None) -> None:
        self._connection = connection

    def probe(self, available_migrations: list[Any] | None = None) -> list[Finding]:
        """Findings for the configured store, first problem first; empty when it is usable."""
        if store_choice("CLAIM_STORE") != "warehouse":
            return []
        from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection, WarehouseNotConfigured

        connection = self._connection or FabricWarehouseConnection()
        try:
            connection.require_configuration()
        except WarehouseNotConfigured as exc:
            return [Finding("warehouse_not_configured", str(exc),
                            _AZURE_REMEDIES["config"] if _azure() else "Set WAREHOUSE_SERVER and WAREHOUSE_DATABASE.")]
        try:
            with connection.connect() as live:
                return self._inspect(live, available_migrations)
        except Exception as exc:  # noqa: BLE001 - classified below; a bug in our code is re-raised
            failure = as_dependency_failure("operational_store", exc)
            if failure is None:
                raise
            log.warning("operational store check failed: %s: %s", type(exc).__name__, str(exc)[:200])
            return [Finding("operational_store_unreachable", f"the operational store {failure.reason}", failure.remedy + (_AZURE_REMEDIES["unreachable"] if _azure() else ""))]

    def _inspect(self, live: Any, available_migrations: list[Any] | None) -> list[Finding]:
        from infrastructure.persistence.schema_admin import applied_migrations, pending_migrations, table_exists

        applied = applied_migrations(live, OPS_SCHEMA)
        if applied is None:
            return [Finding(
                "migration_table_missing", f"{OPS_SCHEMA}.schema_migration not found: the schema was never created here.",
                _AZURE_REMEDIES["bootstrap"] if _azure() else "Run `python scripts/apply-migrations.py --target deployed --bootstrap` on a new Warehouse.",
            )]
        missing = [t for t in _CLAIM_TABLES if not table_exists(live, OPS_SCHEMA, t)]
        if missing:
            return [Finding(
                "tables_missing", f"{OPS_SCHEMA}.{missing[0]} not found: run the migration.",
                "Run `python scripts/apply-migrations.py --target deployed`.",
            )]
        findings: list[Finding] = []
        if available_migrations is not None:
            behind = pending_migrations(available_migrations, applied)
            if behind:
                findings.append(Finding(
                    "migrations_pending", f"{len(behind)} migration(s) not applied, first {behind[0].version}.",
                    _AZURE_REMEDIES["migrate"],
                ))
        return findings + self._grants(live)

    def _grants(self, live: Any) -> list[Finding]:
        remedy = _AZURE_REMEDIES["grants"] if _azure() else "Run `python scripts/grant-warehouse-sql.py --profile api` and check the Fabric workspace role."
        cursor = live.cursor()
        try:
            try:
                cursor.execute(f"SELECT TOP 0 * FROM {OPS_SCHEMA}.program_claim")
            except Exception as exc:  # noqa: BLE001 - a denied SELECT is the finding
                if as_dependency_failure("operational_store", exc) is None:
                    raise
                return [Finding("select_not_granted", f"cannot read {OPS_SCHEMA}.program_claim.", remedy)]
            try:
                cursor.execute(f"SELECT HAS_PERMS_BY_NAME('{OPS_SCHEMA}.program_claim', 'OBJECT', 'INSERT')")
                row = cursor.fetchone()
            except Exception:  # noqa: BLE001 - not every engine can answer; absence of an answer is not a denial
                return [Finding("write_grant_unverified", "could not verify the INSERT grant.", remedy, "warning")]
            if row is not None and row[0] is not None and int(row[0]) == 0:
                return [Finding("insert_not_granted", f"cannot write {OPS_SCHEMA}.program_claim.", remedy)]
            return []
        finally:
            cursor.close()
