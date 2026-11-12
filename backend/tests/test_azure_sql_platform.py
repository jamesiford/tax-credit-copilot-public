"""Azure SQL as the operational store, offline. [09]

Nothing here opens a connection: the tests pin the setting, the allow-list guard, the T-SQL the tooling would
send, and the places where the lakehouse and the Warehouse are different hosts. No Azure SQL database has been
used to write them; the live checks are listed in `report-09` / the ADR.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from application.deployment import normalise_store
from config import get_settings
from infrastructure.persistence import pool_policy
from infrastructure.persistence.schema_admin import (
    Migration,
    TargetMismatch,
    apply_migration,
    discover_migrations,
    load_pinned_targets,
    sha256_text,
)
from infrastructure.persistence.schema_platform import (
    AllowedSqlTarget,
    check_sql_target,
    load_pinned_sql_targets,
    sqlserver_sql,
)
from infrastructure.persistence.sql_errors import DuplicateKey, duplicate_key_as, is_duplicate_key

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
MIGRATIONS = REPO / "docs" / "data" / "schema" / "migrations"


def _script(name: str, filename: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the setting and the store alias ------------------------------------------------------------


def test_the_platform_defaults_to_fabric_and_azure_sql_must_be_asked_for(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_PLATFORM", raising=False)
    assert get_settings().platform.platform == "fabric"
    assert get_settings().platform.pool_max_age_s is None
    monkeypatch.setenv("WAREHOUSE_PLATFORM", "azure_sql")
    assert get_settings().platform.is_azure_sql
    monkeypatch.setenv("WAREHOUSE_PLATFORM", "oracle")
    with pytest.raises(ValueError, match="WAREHOUSE_PLATFORM"):
        _ = get_settings().platform


@pytest.mark.parametrize("spelling", ["fabric", "azure_sql", "sql", "SQL", "warehouse"])
def test_every_spelling_of_the_warehouse_store_normalises_to_the_one_adapter(spelling):
    assert normalise_store(spelling) == "warehouse"


def test_a_local_store_is_still_not_the_warehouse():
    assert normalise_store("sqlite") == "sqlite"


def test_pool_constants_follow_the_override_and_default_to_the_callers(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_POOL_MAX_AGE_SECONDS", raising=False)
    monkeypatch.delenv("WAREHOUSE_POOL_MAX_IDLE", raising=False)
    assert pool_policy.max_age_s(45) == 45 and pool_policy.max_idle(4) == 4
    monkeypatch.setenv("WAREHOUSE_POOL_MAX_AGE_SECONDS", "240")
    monkeypatch.setenv("WAREHOUSE_POOL_MAX_IDLE", "8")
    assert pool_policy.max_age_s(45) == 240 and pool_policy.max_idle(4) == 8
    monkeypatch.setenv("WAREHOUSE_POOL_MAX_AGE_SECONDS", "junk")
    assert pool_policy.max_age_s(45) == 45, "an unparseable tuning value is the default, never a crash"


# --- Part A: the lakehouse is its own host ------------------------------------------------------


def test_the_lakehouse_read_connects_to_the_lakehouse_host_not_the_warehouse_host(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_SERVER", "tcc-sql.database.windows.net")
    monkeypatch.setenv("WAREHOUSE_DATABASE", "tcc")
    monkeypatch.setenv("LAKEHOUSE_SQL_SERVER", "abc123.datawarehouse.fabric.microsoft.com")
    monkeypatch.setenv("LAKEHOUSE_SQL_DATABASE", "payroll_lake")
    monkeypatch.setenv("FABRIC_LAKEHOUSE", "payroll_lake")
    from infrastructure.persistence import source_sql

    source_sql._SHARED_CONNECTION = None
    try:
        reader = source_sql.SourceSqlReader()
        connection = source_sql.shared_connection()
        assert connection.server == "abc123.datawarehouse.fabric.microsoft.com"
        assert connection.database == "payroll_lake"
        assert reader.is_configured()
        assert "tcc-sql.database.windows.net" not in connection.connection_string()
    finally:
        source_sql._SHARED_CONNECTION = None


def test_the_lakehouse_read_is_not_configured_by_the_warehouse_settings_alone(monkeypatch):
    for name in ("LAKEHOUSE_SQL_SERVER", "LAKEHOUSE_SQL_DATABASE", "FABRIC_LAKEHOUSE", "WAREHOUSE_SERVER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WAREHOUSE_DATABASE", "tcc")
    from infrastructure.persistence import source_sql

    source_sql._SHARED_CONNECTION = None
    try:
        assert source_sql.SourceSqlReader().is_configured() is False
    finally:
        source_sql._SHARED_CONNECTION = None


# --- Part B: the guard, the translation, the migration tooling ---------------------------------


ALLOWED = AllowedSqlTarget(name="deployed", server="tcc-sql.database.windows.net", database="tcc", bootstrap_approved=True)


def test_the_guard_passes_only_the_allowed_server_and_database():
    check_sql_target(ALLOWED, server="TCC-SQL.database.windows.net,1433", database="tcc")
    with pytest.raises(TargetMismatch, match="WAREHOUSE_SERVER"):
        check_sql_target(ALLOWED, server="other.database.windows.net", database="tcc")
    with pytest.raises(TargetMismatch, match="WAREHOUSE_DATABASE"):
        check_sql_target(ALLOWED, server="tcc-sql.database.windows.net", database="prod")


def test_a_mismatch_stops_before_any_connection_is_opened(monkeypatch):
    sql_common = _script("sql_common_azure", "sql_common.py")
    monkeypatch.setenv("WAREHOUSE_PLATFORM", "azure_sql")
    monkeypatch.setenv("SQL_SERVER_FQDN", "tcc-sql.database.windows.net")
    monkeypatch.setenv("SQL_DATABASE_NAME", "tcc")
    monkeypatch.setenv("WAREHOUSE_SERVER", "someone-elses.database.windows.net")
    monkeypatch.setenv("WAREHOUSE_DATABASE", "tcc")
    opened = []
    from infrastructure.persistence import fabric_warehouse

    monkeypatch.setattr(fabric_warehouse.FabricWarehouseConnection, "open", lambda self: opened.append(1))
    with pytest.raises(TargetMismatch):
        sql_common.guarded_connection("deployed")
    assert opened == [], "the guard must refuse before a connection exists"


def test_the_deployed_target_needs_the_terraform_outputs_and_approves_the_bootstrap_only_when_created(monkeypatch):
    sql_common = _script("sql_common_azure2", "sql_common.py")
    for name in ("SQL_SERVER_FQDN", "SQL_DATABASE_NAME", "TCC_SQL_CREATED"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(TargetMismatch, match="SQL_SERVER_FQDN"):
        sql_common.allowed_sql_target("deployed")
    monkeypatch.setenv("SQL_SERVER_FQDN", "tcc-sql.database.windows.net")
    monkeypatch.setenv("SQL_DATABASE_NAME", "tcc")
    assert sql_common.allowed_sql_target("deployed").bootstrap_approved is False
    monkeypatch.setenv("TCC_SQL_CREATED", "true")
    assert sql_common.allowed_sql_target("deployed").bootstrap_approved is True


def test_pinned_targets_are_split_by_platform(tmp_path):
    path = tmp_path / "live-targets.json"
    path.write_text(json.dumps({
        "d27": {"workspace_id": "w", "item_id": "i", "endpoint": "e.fabric.example", "database": "d"},
        "sql-test": {"platform": "azure_sql", "server": "t.database.windows.net", "database": "tcc", "bootstrap_approved": True},
    }), encoding="utf-8")
    assert set(load_pinned_targets(path)) == {"d27"}, "the Fabric loader must not choke on, or serve, an Azure SQL entry"
    pinned = load_pinned_sql_targets(path)
    assert set(pinned) == {"sql-test"} and pinned["sql-test"].bootstrap_approved


def test_the_translation_removes_not_enforced_and_nothing_else():
    source = "ALTER TABLE t ADD CONSTRAINT pk PRIMARY KEY NONCLUSTERED (a) NOT ENFORCED;\nGO\nSELECT 'NOT ENFORCED';"
    translated = sqlserver_sql(source)
    assert "PRIMARY KEY NONCLUSTERED (a);" in translated
    assert "SELECT 'NOT ENFORCED';" in translated, "a string literal is not a clause"
    assert sqlserver_sql("SELECT 1") == "SELECT 1"


def test_every_migration_on_disk_translates_to_sql_server_without_the_fabric_clause():
    found = discover_migrations(MIGRATIONS)
    assert found, "no migrations discovered"
    for migration in found:
        text = migration.path.read_text(encoding="utf-8")
        assert not re.search(r"\bNOT\s+ENFORCED\b", sqlserver_sql(text), re.IGNORECASE), migration.path.name


class _Cursor:
    description = None

    def __init__(self, log):
        self._log = log

    def execute(self, sql, *params):
        self._log.append((sql, params))

    def nextset(self):
        return False

    def close(self):
        pass


class _Connection:
    autocommit = True

    def __init__(self):
        self.log = []

    def cursor(self):
        return _Cursor(self.log)


def test_applying_a_migration_on_azure_sql_sends_translated_text_and_records_the_file_hash(tmp_path):
    path = tmp_path / "0099_example.sql"
    text = "ALTER TABLE tcc_ops.x ADD CONSTRAINT pk_x PRIMARY KEY NONCLUSTERED (a) NOT ENFORCED;\nGO\n"
    path.write_text(text, encoding="utf-8")
    migration = Migration("0099", "example", path, sha256_text(text))
    connection = _Connection()

    apply_migration(connection, migration, "tcc_ops", translate=sqlserver_sql)

    sent = " ".join(sql for sql, _ in connection.log)
    assert "NOT ENFORCED" not in sent and "PRIMARY KEY NONCLUSTERED (a)" in sent
    recorded = [params for sql, params in connection.log if "schema_migration" in sql]
    assert recorded and recorded[0][2] == sha256_text(text), "the record is the FILE's hash, so a Fabric and a SQL target agree"


def test_apply_migration_without_a_translator_is_unchanged(tmp_path):
    path = tmp_path / "0098_fabric.sql"
    text = "SELECT 1 NOT ENFORCED_NOT;\n"
    path.write_text(text, encoding="utf-8")
    connection = _Connection()
    apply_migration(connection, Migration("0098", "fabric", path, sha256_text(text)), "tcc_ops")
    assert any("NOT ENFORCED_NOT" in sql for sql, _ in connection.log)


def test_the_bootstrap_ddl_is_the_generated_sql_server_one_on_azure_sql(monkeypatch):
    sql_common = _script("sql_common_azure3", "sql_common.py")
    monkeypatch.delenv("WAREHOUSE_PLATFORM", raising=False)
    assert sql_common.bootstrap_ddl().name == "tcc-schema.fabric.sql"
    assert sql_common.translate_sql("x NOT ENFORCED") == "x NOT ENFORCED"
    monkeypatch.setenv("WAREHOUSE_PLATFORM", "azure_sql")
    assert sql_common.bootstrap_ddl().name == "tcc-schema.sqlserver.sql"
    assert sql_common.translate_sql("x NOT ENFORCED") == "x"


# --- Part C: Entra users and grants -------------------------------------------------------------


@pytest.fixture()
def grant_sql():
    return _script("grant_sql_cli", "grant-sql.py")


def test_the_user_is_created_from_the_external_provider_only_when_absent(grant_sql):
    statement = grant_sql.create_user_statement("tcc-api-identity")
    assert "FROM EXTERNAL PROVIDER" in statement
    assert "sys.database_principals WHERE name = N'tcc-api-identity'" in statement
    assert statement.startswith("IF NOT EXISTS")


def test_no_statement_creates_a_login_or_carries_a_password(grant_sql):
    for profile in ("api", "gateway"):
        text = " ".join(grant_sql.statements_for(profile, "tcc-api", "tcc_gold", "tcc_ops"))
        assert not re.search(r"\b(LOGIN|PASSWORD|WITH PASSWORD|SID)\b", text, re.IGNORECASE)


def test_the_api_profile_reads_and_writes_both_schemas_and_the_gateway_gets_only_the_audit_table(grant_sql):
    api = grant_sql.statements_for("api", "tcc-api", "tcc_gold", "tcc_ops")
    assert api[1:] == [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_gold TO [tcc-api];",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_ops TO [tcc-api];",
    ]
    gateway = grant_sql.statements_for("gateway", "tcc-gw", "tcc_gold", "tcc_ops")
    assert gateway[1:] == ["GRANT INSERT, SELECT ON OBJECT::tcc_ops.channel_audit TO [tcc-gw];"]


def test_a_name_that_could_break_out_of_the_statement_is_refused(grant_sql):
    with pytest.raises(ValueError):
        grant_sql.create_user_statement("x'; DROP USER y; --")


def test_the_dry_run_prints_and_connects_to_nothing(grant_sql, capsys, monkeypatch):
    monkeypatch.setattr(grant_sql.common, "guarded_sql_connection", lambda *a, **k: pytest.fail("connected on a dry run"))
    code = grant_sql.main(["--platform", "azure_sql", "--target", "deployed", "--principal", "tcc-api", "--dry-run"])
    assert code == 0
    assert "CREATE USER [tcc-api] FROM EXTERNAL PROVIDER" in capsys.readouterr().out


# --- Part E: duplicate keys and readiness remedies ---------------------------------------------


def test_the_two_unique_violation_numbers_are_recognised_and_others_are_not():
    assert is_duplicate_key(Exception("('23000', '[23000] [Microsoft][ODBC Driver 18] Violation of PRIMARY KEY constraint (2627)')"))
    assert is_duplicate_key(Exception("Cannot insert duplicate key row ... unique index (2601)"))
    assert not is_duplicate_key(Exception("Snapshot isolation transaction aborted (24556)"))
    assert not is_duplicate_key(Exception("login failed (18456)"))


def test_a_duplicate_key_becomes_one_deliberate_error_and_anything_else_passes_through():
    with pytest.raises(DuplicateKey, match="already recorded"):
        with duplicate_key_as("already recorded"):
            raise Exception("violation (2627)")
    assert issubclass(DuplicateKey, ValueError), "callers that handled the pre-check's ValueError still do"
    with pytest.raises(RuntimeError):
        with duplicate_key_as("already recorded"):
            raise RuntimeError("something else")


def test_a_lost_race_on_the_manifest_insert_reads_as_already_recorded():
    from domain.warehouse import RUN_MANIFEST_COLUMNS
    from infrastructure.persistence.fabric_warehouse import FabricRunManifestRepository
    from tests.test_warehouse_adapter import _manifest

    class Cur:
        def execute(self, sql, *params):
            if not sql.lstrip().upper().startswith("SELECT"):
                raise Exception("Violation of PRIMARY KEY constraint (2627)")

        def executemany(self, sql, rows):
            raise Exception("Violation of PRIMARY KEY constraint (2627)")

        def fetchone(self):
            return None

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            pass

    class Link:
        def connect(self):
            from contextlib import contextmanager

            @contextmanager
            def scope():
                yield Conn()

            return scope()

    assert RUN_MANIFEST_COLUMNS
    with pytest.raises(ValueError, match="already recorded"):
        FabricRunManifestRepository(Link()).record(_manifest())


def test_readiness_names_the_azure_sql_remedies_and_fabric_keeps_its_own(monkeypatch):
    from infrastructure.persistence.store_probe import OperationalStoreProbe

    class NoServer:
        def require_configuration(self):
            from infrastructure.persistence.fabric_warehouse import WarehouseNotConfigured

            raise WarehouseNotConfigured("WAREHOUSE_SERVER not set")

    monkeypatch.setenv("CLAIM_STORE", "warehouse")
    monkeypatch.delenv("WAREHOUSE_PLATFORM", raising=False)
    assert "Fabric" not in OperationalStoreProbe(NoServer()).probe()[0].remedy
    assert OperationalStoreProbe(NoServer()).probe()[0].remedy == "Set WAREHOUSE_SERVER and WAREHOUSE_DATABASE."
    monkeypatch.setenv("WAREHOUSE_PLATFORM", "azure_sql")
    assert "WAREHOUSE_PLATFORM=azure_sql" in OperationalStoreProbe(NoServer()).probe()[0].remedy
