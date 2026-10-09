"""The schema runner: splitting, the live-target guard, and migrations. [D22, D27]

Everything here runs against a fake connection. The point of the guard is that
it refuses BEFORE a statement reaches a Warehouse, so it has to be provable
without one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from infrastructure.persistence import schema_admin as sa

REPO = Path(__file__).resolve().parents[2]
DDL = REPO / "docs" / "data" / "schema" / "tcc-schema.fabric.sql"
SCRIPTS = REPO / "scripts"


# --------------------------------------------------------------------------
# A fake pyodbc connection
# --------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self._sets: list[list[tuple]] = []
        self.description = None

    def execute(self, sql, *params):
        self.conn.executed.append((sql, params))
        sets = self.conn.handler(sql, params)
        self._sets = list(sets or [])
        self._advance()
        return self

    def _advance(self):
        self.description = [("c",)] if self._sets else None

    def fetchall(self):
        return self._sets[0] if self._sets else []

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def nextset(self):
        if self._sets:
            self._sets.pop(0)
        self._advance()
        return bool(self._sets)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, handler=None) -> None:
        self.handler = handler or (lambda sql, params: [])
        self.executed: list[tuple[str, tuple]] = []
        self.autocommit = True
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


# --------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------


def test_go_lines_separate_batches_case_insensitively():
    sql = "CREATE TABLE a (x INT);\nGO\nSELECT 1;\n  go  \nSELECT 2;\nGo -- trailing comment\n"
    assert sa.split_batches(sql) == ["CREATE TABLE a (x INT);", "SELECT 1;", "SELECT 2;"]


def test_a_go_inside_a_block_comment_is_text_not_a_separator():
    sql = "/* header\nGO\nstill a comment */\nSELECT 1;\nGO\nSELECT 2;"
    batches = sa.split_batches(sql)
    assert len(batches) == 2
    assert batches[0].endswith("SELECT 1;") and "GO" in batches[0]


def test_comment_only_batches_are_dropped():
    sql = "/* nothing */\nGO\n-- also nothing\nGO\nSELECT 1;\nGO\n\n"
    assert sa.split_batches(sql) == ["SELECT 1;"]


def test_a_word_containing_go_is_not_a_separator():
    sql = "SELECT 'GO' AS go_value;\nGOTO_LABEL:\nGO\nSELECT 2;"
    assert len(sa.split_batches(sql)) == 2


def test_statements_split_on_terminating_semicolons_only():
    sql = "-- 9.1 first; with a semicolon in the comment\nSELECT 1\nFROM t;\n\n-- 9.2 second\nSELECT ';' AS s;\n"
    statements = sa.split_statements(sql)
    assert len(statements) == 2
    assert sa.statement_label(statements[0]).startswith("9.1")
    assert sa.statement_label(statements[1]).startswith("9.2")


def test_the_bootstrap_ddl_splits_cleanly_and_records_version_0000():
    batches = sa.split_batches(sa.bootstrap_sql(DDL.read_text(encoding="utf-8")))
    assert len(batches) > 50
    assert not any(line.strip().upper() == "GO" for b in batches for line in b.splitlines())
    assert any("INSERT INTO tcc_ops.schema_migration" in b and "'0000'" in b for b in batches)
    # The validation section is NOT part of the bootstrap.
    assert not any("9.1  More than one live claim" in b for b in batches)


def test_the_bootstrap_creates_24_tables():
    batches = sa.split_batches(sa.bootstrap_sql(DDL.read_text(encoding="utf-8")))
    created = {line.split()[2] for b in batches for line in b.splitlines() if line.startswith("CREATE TABLE ")}
    assert len(created) == 24, sorted(created)


def test_section_9_is_every_validation_query_and_nothing_else():
    statements = sa.split_statements(sa.extract_section(DDL.read_text(encoding="utf-8"), "9"))
    assert len(statements) == 25
    assert all(sa._strip_comments(s).strip().upper().startswith("SELECT") for s in statements)
    labels = [sa.statement_label(s) for s in statements]
    assert labels[0].startswith("9.1") and labels[-1].startswith("9.13")


def test_extract_section_refuses_a_missing_section():
    with pytest.raises(ValueError):
        sa.extract_section("/* ===\n  1. ONLY\n=== */\nSELECT 1;", "9")


def test_schemas_are_renamed_only_when_configured():
    sql = "CREATE SCHEMA tcc_gold; SELECT * FROM tcc_ops.run_manifest; -- tcc_gold_extra"
    assert sa.rename_schemas(sql) == sql
    renamed = sa.rename_schemas(sql, gold="g2", ops="o2")
    assert "CREATE SCHEMA g2;" in renamed and "FROM o2.run_manifest" in renamed
    assert "tcc_gold_extra" in renamed, "a longer identifier must not be rewritten"


# --------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------

WS = "11111111-1111-1111-1111-111111111111"
ITEM = "22222222-2222-2222-2222-222222222222"
ENDPOINT = "abc-def.datawarehouse.fabric.microsoft.com"


def _allowed(**overrides):
    base = dict(name="pinned", workspace_id=WS, item_id=ITEM, endpoint=ENDPOINT, database="wh", bootstrap_approved=True)
    base.update(overrides)
    return sa.AllowedTarget(**base)


def _resolved(**overrides):
    base = dict(workspace_id=WS, item_id=ITEM, endpoint=ENDPOINT, display_name="wh")
    base.update(overrides)
    return sa.ResolvedTarget(**base)


def test_the_guard_passes_when_every_identity_agrees():
    sa.check_target(_allowed(), _resolved(), server=f"{ENDPOINT},1433", database="wh")


@pytest.mark.parametrize(
    "resolved, server, database, why",
    [
        (_resolved(workspace_id="99999999-9999-9999-9999-999999999999"), ENDPOINT, "wh", "workspace"),
        (_resolved(item_id="99999999-9999-9999-9999-999999999999"), ENDPOINT, "wh", "item"),
        (_resolved(endpoint="other.datawarehouse.fabric.microsoft.com"), "other.datawarehouse.fabric.microsoft.com", "wh", "endpoint"),
        (_resolved(), "other.datawarehouse.fabric.microsoft.com", "wh", "WAREHOUSE_SERVER"),
        (_resolved(), ENDPOINT, "another_db", "WAREHOUSE_DATABASE"),
    ],
)
def test_the_guard_refuses_any_mismatch(resolved, server, database, why):
    with pytest.raises(sa.TargetMismatch, match=why):
        sa.check_target(_allowed(), resolved, server=server, database=database)


def test_a_deployed_target_takes_its_endpoint_from_resolution_but_still_checks_the_server():
    deployed = _allowed(name="deployed", endpoint=None, database=None)
    sa.check_target(deployed, _resolved(display_name="fresh_wh"), server=ENDPOINT, database="fresh_wh")
    with pytest.raises(sa.TargetMismatch):
        sa.check_target(deployed, _resolved(), server="elsewhere.example", database="wh")


def test_resolution_reads_the_fabric_item_and_refuses_one_with_no_endpoint():
    calls = []

    def get_json(url):
        calls.append(url)
        return {"id": ITEM, "workspaceId": WS, "displayName": "wh", "properties": {"connectionString": ENDPOINT}}

    resolved = sa.resolve_via_fabric_api(WS, ITEM, get_json=get_json)
    assert resolved == _resolved()
    assert calls == [f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/warehouses/{ITEM}"]
    with pytest.raises(sa.TargetMismatch):
        sa.resolve_via_fabric_api(WS, ITEM, get_json=lambda url: {"id": ITEM, "properties": {}})


def test_pinned_targets_load_from_json_and_an_absent_file_pins_nothing(tmp_path):
    assert sa.load_pinned_targets(tmp_path / "missing.json") == {}
    path = tmp_path / "targets.json"
    path.write_text(
        '{"_comment": "x", "demo": {"workspace_id": "%s", "item_id": "%s", "endpoint": "%s", "bootstrap_approved": true}}'
        % (WS, ITEM, ENDPOINT),
        encoding="utf-8",
    )
    pinned = sa.load_pinned_targets(path)
    assert list(pinned) == ["demo"]
    assert pinned["demo"].bootstrap_approved and pinned["demo"].endpoint == ENDPOINT


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


def test_every_result_set_of_a_batch_is_collected():
    conn = FakeConnection(lambda sql, params: [[], [(1, "x")], []])
    [result] = sa.run_batches(conn, ["SELECT 1; SELECT 2; SELECT 3;"])
    assert len(result.result_sets) == 3
    assert result.rows == 1, "a non-empty SECOND result set must not be missed"


def test_a_failing_batch_is_reported_and_stops_the_run():
    def handler(sql, params):
        if "boom" in sql:
            raise RuntimeError("syntax error")
        return []

    conn = FakeConnection(handler)
    results = sa.run_batches(conn, ["SELECT 1;", "boom", "SELECT 3;"])
    assert [r.error is None for r in results] == [True, False]
    results = sa.run_batches(conn, ["SELECT 1;", "boom", "SELECT 3;"], stop_on_error=False)
    assert len(results) == 3


# --------------------------------------------------------------------------
# Migrations
# --------------------------------------------------------------------------


def _write(directory: Path, name: str, text: str = "SELECT 1;\nGO\n") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_migrations_are_discovered_in_version_order(tmp_path):
    _write(tmp_path, "0002_second.sql")
    _write(tmp_path, "0001_first.sql")
    _write(tmp_path, "README.md")
    found = sa.discover_migrations(tmp_path)
    assert [(m.version, m.name) for m in found] == [("0001", "first"), ("0002", "second")]
    assert sa.discover_migrations(tmp_path / "absent") == []


@pytest.mark.parametrize("name", ["1_short.sql", "0001-dash.sql", "0001_Upper.sql", "0000_bootstrap.sql"])
def test_badly_named_or_reserved_migrations_are_refused(tmp_path, name):
    _write(tmp_path, name)
    with pytest.raises(sa.MigrationError):
        sa.discover_migrations(tmp_path)


def test_pending_excludes_recorded_versions_and_refuses_an_edited_one(tmp_path):
    _write(tmp_path, "0001_first.sql")
    _write(tmp_path, "0002_second.sql")
    found = sa.discover_migrations(tmp_path)
    applied = {"0000": "0" * 64, "0001": found[0].sha256}
    assert [m.version for m in sa.pending_migrations(found, applied)] == ["0002"]
    assert sa.pending_migrations(found, {**applied, "0002": found[1].sha256}) == []
    with pytest.raises(sa.MigrationError, match="immutable"):
        sa.pending_migrations(found, {"0001": "f" * 64})


def test_a_migration_is_recorded_only_after_every_batch_succeeds(tmp_path):
    _write(tmp_path, "0001_good.sql", "ALTER TABLE x ADD y INT;\nGO\nUPDATE x SET y = 0;\nGO\n")
    [good] = sa.discover_migrations(tmp_path)
    conn = FakeConnection()
    sa.apply_migration(conn, good, "tcc_ops")
    inserts = [(s, p) for s, p in conn.executed if s.startswith("INSERT INTO tcc_ops.schema_migration")]
    assert len(inserts) == 1 and inserts[0][1] == ("0001", "good", good.sha256)

    bad = _write(tmp_path / "b", "0002_bad.sql", "ALTER TABLE x ADD z INT;\nGO\nboom\nGO\n")
    [bad_m] = sa.discover_migrations(bad.parent)
    conn = FakeConnection(lambda sql, params: (_ for _ in ()).throw(RuntimeError("fail")) if "boom" in sql else [])
    with pytest.raises(sa.MigrationError, match="0002"):
        sa.apply_migration(conn, bad_m, "tcc_ops")
    assert not any(s.startswith("INSERT INTO") for s, _ in conn.executed)


# --------------------------------------------------------------------------
# The CLI's decisions: refuse, bootstrap once, re-run applies nothing
# --------------------------------------------------------------------------


class FakeWarehouse:
    """Just enough Warehouse to answer the runner: does schema_migration exist,
    and what does it hold."""

    def __init__(self, bootstrapped: bool = False) -> None:
        self.has_table = bootstrapped
        self.rows: dict[str, str] = {"0000": "0" * 64} if bootstrapped else {}
        self.bootstrap_batches = 0

    def handler(self, sql, params):
        if "FROM sys.tables" in sql:
            return [[(1 if self.has_table else 0,)]]
        if sql.startswith("SELECT version, sha256 FROM"):
            return [list(self.rows.items())]
        if sql.startswith("INSERT INTO tcc_ops.schema_migration") and params:
            self.rows[params[0]] = params[2]
            return []
        if "DROP TABLE" in sql or "CREATE TABLE" in sql or "CREATE SCHEMA" in sql or "ALTER TABLE" in sql:
            self.bootstrap_batches += 1
        if "CREATE TABLE tcc_ops.schema_migration" in sql:
            self.has_table = True
        if "INSERT INTO tcc_ops.schema_migration" in sql and "'0000'" in sql:
            self.rows["0000"] = "0" * 64
        return []


@pytest.fixture
def migrate_cli(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("apply_migrations_cli", SCRIPTS / "apply-migrations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    common = sys.modules["sql_common"]
    monkeypatch.setattr(common, "MIGRATIONS_DIR", tmp_path / "migrations")
    monkeypatch.setattr(common, "load_env", lambda: None)

    def run(warehouse: FakeWarehouse, *argv, approved: bool = True):
        allowed = _allowed(bootstrap_approved=approved)
        conn = FakeConnection(warehouse.handler)
        monkeypatch.setattr(common, "guarded_connection", lambda name, resolve_only=False: (allowed, _resolved(), conn))
        return module.main(["--target", "pinned", *argv])

    run.migrations = tmp_path / "migrations"
    return run


def test_an_unbootstrapped_warehouse_is_refused_without_the_flag(migrate_cli):
    wh = FakeWarehouse(bootstrapped=False)
    assert migrate_cli(wh) == 1
    assert wh.bootstrap_batches == 0


def test_the_bootstrap_needs_an_approved_target(migrate_cli):
    wh = FakeWarehouse(bootstrapped=False)
    assert migrate_cli(wh, "--bootstrap", approved=False) == 1
    assert wh.bootstrap_batches == 0


def test_bootstrap_once_then_a_rerun_applies_nothing(migrate_cli, capsys):
    wh = FakeWarehouse(bootstrapped=False)
    assert migrate_cli(wh, "--bootstrap") == 0
    first = wh.bootstrap_batches
    assert first > 40 and wh.rows == {"0000": "0" * 64}

    assert migrate_cli(wh, "--bootstrap") == 0, "--bootstrap on a bootstrapped Warehouse is a no-op"
    assert migrate_cli(wh) == 0
    assert wh.bootstrap_batches == first, "the destructive bootstrap must never run twice"
    assert "pending: 0" in capsys.readouterr().out


def test_pending_migrations_are_applied_once_in_order(migrate_cli):
    _write(migrate_cli.migrations, "0002_b.sql")
    _write(migrate_cli.migrations, "0001_a.sql")
    wh = FakeWarehouse(bootstrapped=True)
    assert migrate_cli(wh) == 0
    assert list(wh.rows) == ["0000", "0001", "0002"]
    assert migrate_cli(wh) == 0
    assert list(wh.rows) == ["0000", "0001", "0002"]


# --------------------------------------------------------------------------
# Schema names are configuration (D11)
# --------------------------------------------------------------------------


def test_schema_names_default_to_v2_and_refuse_anything_but_an_identifier(monkeypatch):
    import config

    assert (config.DEFAULT_GOLD_SCHEMA, config.DEFAULT_OPS_SCHEMA) == ("tcc_gold", "tcc_ops")
    monkeypatch.delenv("TCC_TEST_SCHEMA", raising=False)
    assert config.schema_name("TCC_TEST_SCHEMA", "tcc_gold") == "tcc_gold"
    monkeypatch.setenv("TCC_TEST_SCHEMA", "  custom_gold ")
    assert config.schema_name("TCC_TEST_SCHEMA", "tcc_gold") == "custom_gold"
    for bad in ("tcc_gold; DROP TABLE x", "a.b", "1abc", "[x]"):
        monkeypatch.setenv("TCC_TEST_SCHEMA", bad)
        with pytest.raises(ValueError):
            config.schema_name("TCC_TEST_SCHEMA", "tcc_gold")


def test_the_adapters_read_the_configured_schema_names():
    import config
    from infrastructure.persistence import fabric_warehouse, gold_reader, warehouse_gold

    for module in (fabric_warehouse, gold_reader, warehouse_gold):
        assert module.GOLD_SCHEMA == config.GOLD_SCHEMA
        assert module.OPS_SCHEMA == config.OPS_SCHEMA
