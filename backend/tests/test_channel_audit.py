"""The channel audit trail, end to end: auditor, sanitiser, API, CLI, grants. [CH-03]

The repository contracts live in `tests/contracts/test_contract_channel.py`. This
file holds what sits around them: that `audited()` always leaves a closing event,
that a summary can never carry payroll, that the Warehouse adapters send the SQL
they should through the tenant helper, and that the migrations a Warehouse is
asked to run are well-formed.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from application import wiring
from application.channel_audit import AuditCall, ChannelAuditor, request_sha256, summarise_request
from application.identity import ActingUser, NotAuthorized
from domain.channel import ChannelAuditEvent, collapse
from infrastructure.persistence.sqlite_channel import SqliteChannelAuditRepository
from tests.ai_fakes import FakeAgent, foundry_runtime_over, install_providers

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
MIGRATIONS = REPO / "docs" / "data" / "schema" / "migrations"
T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
USER = ActingUser(oid="oid-1", tenant_id="tenant-x", display_name="Test User", upn="t@example.com",
                  channel="teams", conversation_id="conv-1", correlation_id="corr-1")


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def repo(tmp_path):
    repository = SqliteChannelAuditRepository(tmp_path / "audit.db")
    yield repository
    repository.close()


@pytest.fixture
def auditor(repo):
    ids = iter(f"id-{n}" for n in range(1, 100))
    return ChannelAuditor(repo, clock=Clock(), new_id=lambda: next(ids))


def _events(repo):
    return sorted(repo.for_user("oid-1"), key=lambda e: (e.occurred_at, e.event_seq))


# ------------------------------------------------------------------ the sanitiser


def test_a_summary_drops_every_key_that_names_payroll_or_an_employee():
    args = {
        "client_id": 7, "tax_year": 2023, "employee_id": "E123", "Employee_Name": "x",
        "record_token": "t" * 24, "total_wages": 5, "ssn": "000", "payroll_rows": [1, 2],
        "confirmation_token": "tok", "birth_date": "x", "limit": 8,
    }
    summary = summarise_request(args)
    assert summary == "client_id=7, limit=8, tax_year=2023"
    for secret in ("E123", "000", "tok", "wages", "ssn"):
        assert secret not in summary


def test_nested_sensitive_keys_are_dropped_and_lists_are_counted_not_listed():
    summary = summarise_request({"filter": {"state": "GA", "employee_id": "E9"}, "sites": ["a", "b", "c"], "none": None})
    assert summary == "filter={state=GA}, sites=[3 items]"


def test_long_values_and_long_summaries_are_truncated():
    assert summarise_request({"note": "x" * 500}) == "note=" + "x" * 80
    wide = summarise_request({f"k{n:03d}": "v" * 60 for n in range(100)}, limit=300)
    assert len(wide) == 300 and wide.endswith("…")


def test_the_hash_covers_the_whole_request_including_what_the_summary_drops():
    a = {"client_id": 1, "employee_id": "E1"}
    b = {"client_id": 1, "employee_id": "E2"}
    assert summarise_request(a) == summarise_request(b)
    assert request_sha256(a) != request_sha256(b)
    assert request_sha256(a) == request_sha256({"employee_id": "E1", "client_id": 1})
    assert request_sha256(a) == hashlib.sha256(b'{"client_id":1,"employee_id":"E1"}').hexdigest()


# --------------------------------------------------------------------- audited()


def test_a_read_writes_one_single_event(auditor, repo):
    with auditor.audited(AuditCall("book_rank", "read", USER, {"limit": 8})) as handle:
        handle.annotate(run_id="run-1", trail_sha256="a" * 64, numeric_guard="pass")
    [event] = _events(repo)
    assert (event.phase, event.event_seq, event.outcome) == ("single", 1, "ok")
    assert (event.tool_name, event.action_kind, event.run_id, event.numeric_guard) == ("book_rank", "read", "run-1", "pass")
    assert event.request_summary == "limit=8" and event.elapsed_ms == 1000
    assert (event.user_oid, event.user_upn, event.channel, event.conversation_id) == ("oid-1", "t@example.com", "teams", "conv-1")
    assert event.correlation_id == "corr-1" and event.identity_assurance == "channel-asserted"


def test_a_write_is_a_pending_begin_then_an_end_sharing_one_audit_id(auditor, repo):
    call = AuditCall("claim_transition_commit", "write_commit", USER, {"status": "proposed"}, client_id=5, tax_year=2024)
    with auditor.audited(call) as handle:
        assert [e.phase for e in _events(repo)] == ["begin"], "the record exists BEFORE the work runs"
        assert _events(repo)[0].outcome == "pending"
        handle.annotate(confirmation_ref="conf-1")
    begin, end = _events(repo)
    assert (begin.audit_id, end.audit_id) == ("id-1", "id-1")
    assert (begin.event_seq, end.event_seq, end.phase, end.outcome) == (1, 2, "end", "ok")
    assert end.confirmation_ref == "conf-1" and (end.client_id, end.tax_year) == (5, 2024)
    assert begin.request_summary == "status=proposed" and end.request_summary is None
    [entry] = collapse(_events(repo))
    assert entry.outcome == "ok"


def test_an_exception_still_closes_the_request_as_an_error_and_is_reraised(auditor, repo):
    with pytest.raises(RuntimeError, match="boom"):
        with auditor.audited(AuditCall("claim_record_commit", "write_commit", USER)):
            raise RuntimeError("boom")
    end = _events(repo)[-1]
    assert (end.phase, end.outcome, end.error) == ("end", "error", "RuntimeError: boom")


def test_a_refusal_is_recorded_as_refused_not_as_a_fault(auditor, repo):
    with pytest.raises(NotAuthorized):
        with auditor.audited(AuditCall("claim_record_commit", "write_commit", USER)):
            raise NotAuthorized("not a writer")
    end = _events(repo)[-1]
    assert (end.outcome, end.error) == ("refused", "not a writer")


def test_a_failing_read_is_recorded_as_one_error_event(auditor, repo):
    with pytest.raises(ValueError):
        with auditor.audited(AuditCall("client_trend", "read", USER)):
            raise ValueError("no client")
    [event] = _events(repo)
    assert (event.phase, event.outcome) == ("single", "error")


def test_a_guard_rejection_is_the_outcome_the_work_reports(auditor, repo):
    with auditor.audited(AuditCall("client_eligibility", "read", USER)) as handle:
        handle.annotate(outcome="rejected_by_guard", numeric_guard="rejected")
    [event] = _events(repo)
    assert (event.outcome, event.numeric_guard) == ("rejected_by_guard", "rejected")


def test_a_crash_between_begin_and_end_leaves_a_pending_entry(auditor, repo):
    handle = auditor.begin_write(AuditCall("claim_transition_commit", "write_commit", USER, client_id=5))
    assert handle.audit_id == "id-1"
    [entry] = collapse(_events(repo))
    assert entry.outcome == "pending" and entry.finished_at is None


def test_nothing_proceeds_if_the_opening_event_cannot_be_written(repo):
    class Down:
        def append(self, event):
            raise ConnectionError("warehouse unreachable")

    ran = []
    with pytest.raises(ConnectionError):
        with ChannelAuditor(Down()).audited(AuditCall("claim_record_commit", "write_commit", USER)):
            ran.append("write")
    assert ran == []


def test_a_failure_writing_the_closing_event_does_not_mask_the_result(repo, caplog):
    class FailsOnEnd:
        def __init__(self):
            self.events = []

        def append(self, event):
            if event.phase == "end":
                raise ConnectionError("gone")
            self.events.append(event)

    store = FailsOnEnd()
    with ChannelAuditor(store).audited(AuditCall("claim_record_commit", "write_commit", USER)):
        pass
    assert [e.phase for e in store.events] == ["begin"]
    assert "closing channel audit event" in caplog.text


def test_an_unattributed_caller_is_recorded_as_anonymous(auditor, repo):
    auditor.record_read(AuditCall("book_rank", "read", None))
    [event] = repo.for_user("anonymous")
    assert event.channel == "api-test" and event.identity_assurance == "channel-asserted"


def test_a_correlation_id_is_generated_when_the_caller_has_none(auditor, repo):
    lone = ActingUser(oid="oid-1", channel="teams")
    auditor.record_read(AuditCall("book_rank", "read", lone))
    assert _events(repo)[0].correlation_id == "id-2"


def test_an_annotation_cannot_overwrite_the_identity_of_the_request(auditor):
    handle = auditor.begin_write(AuditCall("claim_record_commit", "write_commit", USER))
    with pytest.raises(AttributeError):
        handle.annotate(audit_id="other")
    with pytest.raises(AttributeError):
        handle.annotate(nonsense=1)


# ----------------------------------------------------- the Warehouse adapter's SQL


class _Cursor:
    def __init__(self, conn):
        self.conn, self.description, self.rowcount = conn, None, 1

    def execute(self, sql, params=None):
        self.conn.statements.append((" ".join(sql.split()), list(params or [])))
        if sql.lstrip().startswith("SELECT"):
            self.description = [(name,) for name in self.conn.columns]
        return self

    def fetchall(self):
        return self.conn.rows

    def close(self):
        pass


class _Conn:
    def __init__(self, columns=(), rows=()):
        self.statements, self.columns, self.rows = [], list(columns), list(rows)
        self.autocommit = True

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


class _Warehouse:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        from contextlib import contextmanager

        @contextmanager
        def scope():
            yield self.conn

        return scope()


def _event(client_id=None, **kw) -> ChannelAuditEvent:
    values = dict(audit_id="a", event_seq=1, phase="single", correlation_id="c", channel="teams", user_oid="u",
                  identity_assurance="channel-asserted", tool_name="book_rank", action_kind="read", outcome="ok",
                  occurred_at=T0, client_id=client_id)
    values.update(kw)
    return ChannelAuditEvent(**values)


def test_an_event_naming_a_client_is_inserted_under_that_tenant():
    from infrastructure.persistence.warehouse_channel import WarehouseChannelAuditRepository

    conn = _Conn()
    WarehouseChannelAuditRepository(_Warehouse(conn)).append(_event(client_id=42))
    sql, params = conn.statements[0]
    assert sql.startswith("INSERT INTO tcc_ops.channel_audit (")
    assert params[conn_columns().index("client_id")] == 42


def conn_columns():
    from infrastructure.persistence.sqlite_channel import EVENT_COLUMNS

    return list(EVENT_COLUMNS)


def test_an_event_naming_no_client_goes_through_the_logged_exemption(caplog):
    import logging

    from infrastructure.persistence.warehouse_channel import WarehouseChannelAuditRepository

    conn = _Conn()
    with caplog.at_level(logging.INFO, logger="tcc.tenant_sql"):
        WarehouseChannelAuditRepository(_Warehouse(conn)).append(_event())
    assert any("names no client has no tenant to bind" in r.message for r in caplog.records)
    assert conn.statements[0][1][conn_columns().index("client_id")] is None


def test_the_by_user_read_is_parameterised_and_newest_first():
    from infrastructure.persistence.warehouse_channel import WarehouseChannelAuditRepository

    conn = _Conn()
    repo = WarehouseChannelAuditRepository(_Warehouse(conn))
    assert repo.for_user("oid-1", since=T0, until=T0 + timedelta(days=1), tool="book_rank", limit=25) == []
    sql, params = conn.statements[0]
    assert sql.startswith("SELECT TOP 25 ") and "WHERE user_oid = ?" in sql
    assert sql.endswith("ORDER BY occurred_at DESC, event_seq DESC")
    assert params[0] == "oid-1" and params[-1] == "book_rank" and len(params) == 4
    assert "oid-1" not in sql and "book_rank" not in sql, "values are bound, never interpolated"


def test_the_limit_cannot_inject_sql():
    from infrastructure.persistence.warehouse_channel import WarehouseChannelAuditRepository

    with pytest.raises(ValueError):
        WarehouseChannelAuditRepository(_Warehouse(_Conn())).for_user("u", limit="5; DROP TABLE x")


def test_a_confirmation_is_consumed_by_a_guarded_update():
    from infrastructure.persistence.warehouse_channel_state import WarehouseConfirmationRepository

    conn = _Conn()
    assert WarehouseConfirmationRepository(_Warehouse(conn)).consume("c1", T0, "k") is True
    sql, params = conn.statements[0]
    assert sql.startswith("UPDATE tcc_ops.channel_confirmation SET consumed_at = ?")
    assert "WHERE confirmation_id = ? AND consumed_at IS NULL" in sql and params[-1] == "c1"


# ------------------------------------------------------------------- migrations


def _migration_files():
    return sorted(MIGRATIONS.glob("0*.sql"))


def test_the_channel_migrations_are_discovered_in_order():
    from infrastructure.persistence import schema_admin as sa

    found = sa.discover_migrations(MIGRATIONS)
    assert [(m.version, m.name) for m in found] == [("0001", "channel_audit"), ("0002", "engagement_actor")]
    assert all(len(m.sha256) == 64 for m in found)


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.name)
def test_a_migration_is_go_separated_and_avoids_forbidden_constructs(path):
    from infrastructure.persistence import schema_admin as sa

    text = path.read_text(encoding="utf-8")
    batches = sa.split_batches(text)
    assert batches and all(not sa.is_blank(b) for b in batches)
    assert text.rstrip().endswith("GO"), "every batch is terminated"
    code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for forbidden in (r"CREATE\s+(UNIQUE\s+)?(CLUSTERED\s+|NONCLUSTERED\s+)?INDEX", r"\bIDENTITY\b", r"\bMERGE\b"):
        assert not re.search(forbidden, code, re.I), f"{path.name} uses {forbidden}"
    assert not re.search(r"\b(DROP|TRUNCATE)\s+TABLE", code, re.I), "migrations are forward-only and non-destructive"
    for batch in sa.split_batches(code):
        assert batch.strip().upper().startswith(("CREATE TABLE", "ALTER TABLE")), batch[:60]


def test_0001_creates_the_three_channel_tables_with_the_specified_columns():
    code = (MIGRATIONS / "0001_channel_audit.sql").read_text(encoding="utf-8")
    for table in ("channel_audit", "channel_user", "channel_confirmation"):
        assert f"CREATE TABLE tcc_ops.{table}" in code
    audit = re.search(r"CREATE TABLE tcc_ops\.channel_audit\s*\((.*?)\n\);", code, re.S).group(1)
    columns = [line.split()[0] for line in audit.splitlines() if line.strip() and not line.strip().startswith("--")]
    from infrastructure.persistence.sqlite_channel import EVENT_COLUMNS

    assert columns == list(EVENT_COLUMNS), "the adapters and the DDL must name the same columns, in order"
    assert "PRIMARY KEY NONCLUSTERED (audit_id, event_seq) NOT ENFORCED" in code
    assert "token_sha256" in code and not re.search(r"\btoken\s+VARCHAR", code)
    for name, kind in (("elapsed_ms", "INT"), ("occurred_at", "DATETIME2(3)"), ("is_deterministic_path", "BIT"),
                       ("request_summary", "VARCHAR(2000)")):
        assert re.search(rf"\b{name}\s+{re.escape(kind)}(?!\w)", audit), name


def test_0002_adds_only_nullable_actor_columns_to_program_engagement():
    code = (MIGRATIONS / "0002_engagement_actor.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE tcc_ops.program_engagement ADD set_by VARCHAR(256) NULL" in code
    assert "ALTER TABLE tcc_ops.program_engagement ADD set_at DATETIME2(3) NULL" in code
    assert "NOT NULL" not in re.sub(r"/\*.*?\*/", "", code, flags=re.S)


@pytest.fixture
def migrate_real(monkeypatch):
    """The real runner and the real migration folder, against the existing fake Warehouse."""
    sys.path.insert(0, str(SCRIPTS))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import test_schema_admin as fake

    spec = importlib.util.spec_from_file_location("apply_migrations_cli", SCRIPTS / "apply-migrations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    common = sys.modules["sql_common"]
    monkeypatch.setattr(common, "MIGRATIONS_DIR", MIGRATIONS)
    monkeypatch.setattr(common, "load_env", lambda: None)

    def run(warehouse):
        conn = fake.FakeConnection(warehouse.handler)
        monkeypatch.setattr(
            common, "guarded_connection",
            lambda name, resolve_only=False: (fake._allowed(bootstrap_approved=True), fake._resolved(), conn),
        )
        return module.main(["--target", "pinned"])

    return run, fake.FakeWarehouse


def test_apply_migrations_reports_two_pending_on_a_fresh_store_then_none(migrate_real, capsys):
    run, FakeWarehouse = migrate_real
    warehouse = FakeWarehouse(bootstrapped=True)
    assert run(warehouse) == 0
    assert list(warehouse.rows) == ["0000", "0001", "0002"]
    out = capsys.readouterr().out
    assert "pending: 2" in out
    assert run(warehouse) == 0
    assert "pending: 0" in capsys.readouterr().out
    assert list(warehouse.rows) == ["0000", "0001", "0002"], "a re-run applies nothing"


# ------------------------------------------------------------------ the query API


@pytest.fixture
def api(repo):
    from fastapi.testclient import TestClient

    from application.wiring import set_channel_audit_repository
    from main import app

    set_channel_audit_repository(repo)
    yield TestClient(app)
    set_channel_audit_repository(None)


def test_the_audit_endpoint_returns_events_newest_first_and_a_pending_entry(api, auditor, repo):
    auditor.record_read(AuditCall("book_rank", "read", USER))
    auditor.begin_write(AuditCall("claim_transition_commit", "write_commit", USER, client_id=5))
    body = api.get("/api/audit/channel", params={"user_oid": "oid-1"}).json()
    assert [e["tool_name"] for e in body["events"]] == ["claim_transition_commit", "book_rank"]
    assert [(e["tool_name"], e["outcome"]) for e in body["entries"]] == [
        ("claim_transition_commit", "pending"), ("book_rank", "ok")]


def test_the_audit_endpoint_filters_by_tool_and_window(api, auditor):
    auditor.record_read(AuditCall("book_rank", "read", USER))
    auditor.record_read(AuditCall("client_trend", "read", USER))
    by_tool = api.get("/api/audit/channel", params={"user_oid": "oid-1", "tool": "client_trend"}).json()
    assert [e["tool_name"] for e in by_tool["events"]] == ["client_trend"]
    future = api.get("/api/audit/channel", params={"user_oid": "oid-1", "since": "2099-01-01T00:00:00Z"}).json()
    assert future["events"] == [] and future["entries"] == []


@pytest.mark.parametrize("params", [{}, {"user_oid": ""}, {"user_oid": "u", "limit": 501}, {"user_oid": "u", "limit": 0}])
def test_the_audit_endpoint_refuses_a_malformed_query(api, params):
    assert api.get("/api/audit/channel", params=params).status_code == 422


def test_the_route_is_declared_in_the_inventory():
    inventory = json.loads((Path(__file__).parent / "route_inventory.json").read_text(encoding="utf-8"))
    assert "GET /api/audit/channel" in inventory


# ------------------------------------------------------------------ the CLI


@pytest.fixture
def audit_cli(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("channel_audit_cli", SCRIPTS / "channel-audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys.modules["sql_common"], "load_env", lambda: None)
    return module


class _NoWriters:
    def live(self):
        return []


def test_the_cli_prints_a_per_user_timeline_with_pending_marked(audit_cli, auditor, repo, capsys):
    auditor.record_read(AuditCall("book_rank", "read", USER))
    auditor.begin_write(AuditCall("claim_transition_commit", "write_commit", USER, client_id=5, tax_year=2024))
    assert audit_cli.main(["--user", "oid-1"], repository=repo, writers=_NoWriters()) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert "PENDING" in lines[0] and "claim_transition_commit" in lines[0] and "client 5 TY2024" in lines[0]
    assert "ok" in lines[1] and "no client" in lines[1]


def test_the_cli_resolves_a_name_through_the_writer_allow_list(audit_cli, auditor, repo, capsys):
    from domain.channel import WriterGrant

    class Writers:
        def live(self):
            return [WriterGrant(user_oid="oid-1", added_by="op", display_name="Test User")]

    auditor.record_read(AuditCall("book_rank", "read", USER))
    assert audit_cli.main(["--user", "test user"], repository=repo, writers=Writers()) == 0
    assert "book_rank" in capsys.readouterr().out
    assert audit_cli.main(["--user", "Nobody At All"], repository=repo, writers=Writers()) == 2


def test_the_cli_reports_no_activity_and_refuses_a_bad_date(audit_cli, repo, capsys):
    assert audit_cli.main(["--user", "oid-9"], repository=repo, writers=_NoWriters()) == 0
    assert "(no channel activity)" in capsys.readouterr().out
    assert audit_cli.main(["--user", "oid-9", "--since", "yesterday-ish"], repository=repo, writers=_NoWriters()) == 2


# --------------------------------------------------------------- warehouse grants


@pytest.fixture
def grants(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("grant_cli", SCRIPTS / "grant-warehouse-sql.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys.modules["sql_common"], "load_env", lambda: None)
    return module


def test_the_api_profile_still_grants_both_schemas(grants):
    assert grants.statements_for("api", "tcc-api", "tcc_gold", "tcc_ops") == [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_gold TO [tcc-api];",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_ops TO [tcc-api];",
    ]


def test_the_gateway_profile_grants_insert_and_select_on_the_audit_table_only(grants):
    statements = grants.statements_for("gateway", "tcc-gateway", "tcc_gold", "tcc_ops")
    assert statements == ["GRANT INSERT, SELECT ON OBJECT::tcc_ops.channel_audit TO [tcc-gateway];"]
    text = " ".join(statements)
    for withheld in ("SCHEMA::", "UPDATE", "DELETE", "tcc_gold", "channel_user", "channel_confirmation"):
        assert withheld not in text


@pytest.mark.parametrize("principal", ["x]; DROP USER y;--", "a'b", "", "x" * 200])
def test_an_unusual_principal_is_refused_for_both_profiles(grants, principal):
    with pytest.raises(ValueError):
        grants.statements_for("api", principal, "tcc_gold", "tcc_ops")
    with pytest.raises(ValueError):
        grants.statements_for("gateway", principal, "tcc_gold", "tcc_ops")


def test_an_unusual_schema_or_object_is_refused(grants):
    with pytest.raises(ValueError):
        grants.gateway_grant_statements("tcc-gw", "tcc_ops; DROP TABLE x")
    with pytest.raises(ValueError):
        grants.gateway_grant_statements("tcc-gw", "tcc_ops", ("channel_audit TO [evil]; --",))


def test_the_gateway_dry_run_prints_its_one_grant(grants, capsys, monkeypatch):
    monkeypatch.setenv("GATEWAY_IDENTITY_NAME", "tcc-gw-identity")
    assert grants.main(["--target", "deployed", "--profile", "gateway", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == "GRANT INSERT, SELECT ON OBJECT::tcc_ops.channel_audit TO [tcc-gw-identity];"


# --------------------------------------------------------------- agent action audit


class _FakeAgent(FakeAgent):
    """The shared fake, under the name this file has always used."""


@pytest.fixture
def action_repo(tmp_path):
    from application.wiring import set_agent_action_audit_repository
    from infrastructure.persistence.sqlite_channel import SqliteAgentActionAuditRepository

    repository = SqliteAgentActionAuditRepository(tmp_path / "actions.db")
    set_agent_action_audit_repository(repository)
    yield repository
    set_agent_action_audit_repository(None)
    repository.close()


def _drive(agent, prompt="Brief: $3,500 for E123"):
    import api.chat as chat

    async def run():
        from types import SimpleNamespace

        install_providers(foundry_runtime_over(agent))
        app = SimpleNamespace(state=SimpleNamespace())
        token = chat._TELEMETRY_CONTEXT.set({"app": app, "request_id": "r", "intent": "book"})
        actor = chat._ACTOR.set("analyst@example.com")
        try:
            return [frame async for frame in chat._stream_agent("ClientSituationAgent", prompt)]
        finally:
            chat._ACTOR.reset(actor)
            chat._TELEMETRY_CONTEXT.reset(token)
            wiring.reset_ai()

    return asyncio.run(run())


def test_a_chat_agent_call_writes_one_audit_row_without_changing_the_stream(action_repo):
    prompt = "Brief: $3,500 for E123"
    frames = _drive(_FakeAgent(), prompt)
    assert [f.split("\n")[0] for f in frames] == [
        "event: agent_start", "event: token", "event: token", "event: agent_end"]
    assert '"content":"Hello "' in frames[1] and '"content":"world"' in frames[2]

    [row] = action_repo.recent()
    assert row.agent_name == "ClientSituationAgent" and row.agent_version == "7"
    assert row.prompt_hash == hashlib.sha256(prompt.encode()).hexdigest()
    assert json.loads(row.tool_calls) == ["book_rank"]
    assert row.user_upn == "analyst@example.com"
    assert row.is_deterministic_path is False, "chat prose is not validated, and the row must not claim it is"
    assert row.output_summary == "status=ok; output_chars=11"
    assert "3,500" not in (row.input_summary or "") and "E123" not in (row.input_summary or "")
    assert prompt not in (row.input_summary or "") + (row.output_summary or "")


def test_a_failed_agent_call_is_recorded_as_failed(action_repo):
    _drive(_FakeAgent(fail=True))
    [row] = action_repo.recent()
    assert row.output_summary.startswith("status=failed")


def test_an_audit_outage_does_not_break_the_stream(monkeypatch, tmp_path):
    from application.wiring import set_agent_action_audit_repository

    class Down:
        def append(self, action):
            raise ConnectionError("down")

    set_agent_action_audit_repository(Down())
    try:
        frames = _drive(_FakeAgent())
    finally:
        set_agent_action_audit_repository(None)
    assert len(frames) == 4 and frames[-1].startswith("event: agent_end")


def test_the_stream_is_byte_identical_with_and_without_the_hook(action_repo, monkeypatch):
    import api.chat.narration as narration

    with_hook = _drive(_FakeAgent())
    monkeypatch.setattr(narration, "_record_agent_action", lambda *a, **k: None)
    assert _drive(_FakeAgent()) == with_hook


# ------------------------------------------------------------ stores and deployment


def test_the_channel_store_defaults_to_sqlite_locally_and_the_warehouse_when_deployed():
    from application.deployment import store_choice

    assert store_choice("CHANNEL_STORE", {}) == "sqlite"
    assert store_choice("CHANNEL_STORE", {"ENVIRONMENT": "azure"}) == "warehouse"
    assert store_choice("CHANNEL_STORE", {"ENVIRONMENT": "azure", "CHANNEL_STORE": "fabric"}) == "warehouse"


@pytest.mark.parametrize("value", ["sqlite", "memory"])
def test_a_deployed_process_refuses_a_non_durable_channel_store(value):
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    env = {"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", "CLAIM_STORE": "warehouse",
           "AUTH_MODE": "none", "ALLOW_ANONYMOUS_SYNTHETIC": "1",
           "FINDING_STORE": "warehouse", "RUN_MANIFEST_STORE": "warehouse", "ARTIFACT_STORE": "blob",
           "ARTIFACT_REPOSITORY": "warehouse", "CHANNEL_STORE": value}
    with pytest.raises(DeploymentConfigurationError, match="CHANNEL_STORE"):
        check_deployment_configuration(env)
    del env["CHANNEL_STORE"]
    assert check_deployment_configuration(env)["CHANNEL_STORE"] == "warehouse"


def test_the_wiring_selects_the_adapter_the_store_names(monkeypatch, tmp_path):
    from application import wiring
    from infrastructure.persistence.sqlite_channel import SqliteChannelAuditRepository
    from infrastructure.persistence.sqlite_channel_state import SqliteConfirmationRepository, SqliteWriterRepository

    monkeypatch.setenv("OPERATIONAL_DB", str(tmp_path / "ops.db"))
    for setter in (wiring.set_channel_audit_repository, wiring.set_writer_repository, wiring.set_confirmation_repository):
        setter(None)
    try:
        assert isinstance(wiring.get_channel_audit_repository(), SqliteChannelAuditRepository)
        assert isinstance(wiring.get_writer_repository(), SqliteWriterRepository)
        assert isinstance(wiring.get_confirmation_repository(), SqliteConfirmationRepository)
        monkeypatch.setenv("CHANNEL_STORE", "nonsense")
        wiring.set_channel_audit_repository(None)
        with pytest.raises(ValueError, match="CHANNEL_STORE"):
            wiring.get_channel_audit_repository()
    finally:
        for setter in (wiring.set_channel_audit_repository, wiring.set_writer_repository, wiring.set_confirmation_repository):
            setter(None)
