"""Failures are typed, visible and bounded: no silent fallback, an explicit `degraded` list. [03.7]

`GET /api/v2/portfolio` used to answer an unreachable claims store with an opaque 500, and an
unreachable or unconfigured source with a 200 and an empty book that read as "no clients". Claims and
engagements are app-owned and have no copy anywhere else, so for them there is nothing to fall back
to; for the source the old fallback was a ten-table Delta read of every payroll row. Now each outage is
named, with its remedy, and the page says what it could not read.
"""
from __future__ import annotations

import contextlib

import pytest
from fastapi.testclient import TestClient

from application import client_book
from application.errors import DependencyUnavailable, as_dependency_failure
from application.queries import portfolio_reads


class _Broken:
    """A claim repository whose reads raise, as an unreachable or uninitialised warehouse does."""

    def __init__(self, error: Exception):
        self.error = error

    def portfolio_coverage(self, **_kw):
        raise self.error

    def engagements(self, *_a, **_kw):
        raise self.error


@pytest.fixture
def api(tmp_path, monkeypatch):
    from bootstrap import wiring
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from main import app

    repo = SqliteClaimRepository(tmp_path / "claims.db")
    wiring.set_claim_repository(repo)
    monkeypatch.setattr(portfolio_reads, "_footprint_failure", None)
    yield TestClient(app, raise_server_exceptions=False), wiring
    repo.close()
    wiring.set_claim_repository(None)


@pytest.fixture
def no_full_delta_read(monkeypatch):
    """The safety net behind every test here: the full ten-table load must never be the fallback."""
    from data.source.from_fabric import FabricLakehouseReader

    def forbidden(self, account_id):
        raise AssertionError("the full Delta read was used as a fallback")

    monkeypatch.setattr(FabricLakehouseReader, "for_account", forbidden)


def _degraded(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return response.json()["degraded"]


def _dependencies(entries) -> set[str]:
    return {entry["dependency"] for entry in entries}


# ------------------------------------------------------------ claims store


def test_an_unreachable_claims_store_is_degraded_with_a_remedy_not_an_opaque_500(api, no_full_delta_read):
    client, wiring = api
    wiring.set_claim_repository(_Broken(OSError("08001 connection to the warehouse timed out")))
    response = client.get("/api/v2/portfolio")
    (entry,) = _degraded(response)
    assert entry["dependency"] == "claims_store"
    assert "unavailable" in entry["impact"]
    assert "network" in entry["remedy"].lower() or "server" in entry["remedy"].lower()
    body = response.json()
    assert body["total"] == 1, "the book still lists its clients"
    assert body["items"][0]["identified_usd"] is None, "no figure is invented for a client whose claims could not be read"


def test_an_uninitialised_store_says_to_run_the_migration(api, no_full_delta_read):
    client, wiring = api
    wiring.set_claim_repository(_Broken(RuntimeError("Invalid object name 'tcc_ops.program_claim'.")))
    (entry,) = _degraded(client.get("/api/v2/portfolio"))
    assert entry["dependency"] == "claims_store"
    assert "apply-migrations" in entry["remedy"]


def test_a_denied_grant_says_to_grant(api):
    client, wiring = api
    wiring.set_claim_repository(_Broken(RuntimeError("The SELECT permission was denied on the object 'program_claim'")))
    (entry,) = _degraded(client.get("/api/v2/portfolio"))
    assert "grant" in entry["remedy"].lower()


def test_an_empty_claims_table_is_normal_not_degraded(api, no_full_delta_read):
    client, _ = api
    body = client.get("/api/v2/portfolio").json()
    assert body["degraded"] == []
    assert body["total_clients"] == 1 and body["assessed_clients"] == 0 and body["unassessed_clients"] == 1


def test_a_bug_in_our_code_is_not_reported_as_an_outage(api):
    client, wiring = api
    wiring.set_claim_repository(_Broken(TypeError("unsupported operand")))
    assert client.get("/api/v2/portfolio").status_code == 500


def test_the_engagement_read_failing_after_the_claims_read_is_degraded_too(api, monkeypatch):
    client, wiring = api
    repo = wiring.get_claim_repository()
    from domain.claims import ClaimStatus, Provenance

    client.post("/api/claims", json={
        "client_id": 1001, "program_code": "GA_JTC", "tax_year": 2023, "status": "assessed",
        "provenance": "computed", "decided_by": "a@example.com", "identified_usd": "100",
    })
    monkeypatch.setattr(repo, "engagements", lambda *_a, **_k: (_ for _ in ()).throw(OSError("timed out")))
    monkeypatch.setattr("infrastructure.persistence.engagement_batch.EngagementBatchReader.read", lambda self, repo, ids: None)  # the per-client read is what is under test
    entries = _degraded(client.get("/api/v2/portfolio"))
    assert _dependencies(entries) == {"claims_store"}
    assert any("engagement" in e["impact"] for e in entries)


# --------------------------------------------------------------- the source


def test_a_source_that_raises_is_degraded_and_the_claims_still_answer(api, monkeypatch, no_full_delta_read):
    client, _ = api
    client.post("/api/claims", json={
        "client_id": 1001, "program_code": "GA_JTC", "tax_year": 2023, "status": "assessed",
        "provenance": "computed", "decided_by": "a@example.com", "identified_usd": "100",
    })

    def down():
        raise OSError("getaddrinfo failed: private host does not resolve")

    monkeypatch.setattr(client_book, "clients", down)
    response = client.get("/api/v2/portfolio")
    (entry,) = _degraded(response)
    assert entry["dependency"] == "source_lakehouse" and "client book" in entry["impact"]
    assert response.json()["total"] == 1, "the assessed client is still listed from its claim"


def test_an_unconfigured_lakehouse_is_degraded_naming_the_settings_not_an_empty_book(api, monkeypatch, no_full_delta_read):
    client, _ = api
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    for name in ("FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"):
        monkeypatch.delenv(name, raising=False)
    (entry,) = _degraded(client.get("/api/v2/portfolio"))
    assert entry["dependency"] == "source_lakehouse"
    assert "FABRIC_WORKSPACE" in entry["remedy"] and "FABRIC_LAKEHOUSE" in entry["remedy"]


def test_a_source_that_answers_with_no_clients_is_an_empty_book_not_degraded(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(client_book, "clients", lambda: [])
    body = client.get("/api/v2/portfolio").json()
    assert body["degraded"] == [] and body["total"] == 0


class _FakeSql:
    def __init__(self):
        self.calls = 0

    def is_configured(self):
        return True

    def footprint(self, **_guard):
        self.calls += 1
        raise OSError("timed out")


def test_a_failed_footprint_is_degraded_and_is_not_rescanned_on_every_view(api, monkeypatch, no_full_delta_read):
    client, _ = api
    fake = _FakeSql()
    monkeypatch.setattr("tools.fabric_source.active_data_source", lambda: "lakehouse")
    monkeypatch.setattr(client_book, "clients", lambda: [{"account_id": 1001, "name": "A", "industry": None}])
    monkeypatch.setattr("application.source_ports.new_source_reader", lambda: fake)
    first = _degraded(client.get("/api/v2/portfolio"))
    second = _degraded(client.get("/api/v2/portfolio"))
    assert _dependencies(first) == _dependencies(second) == {"source_sql"}
    assert fake.calls == 1, "a source that is down is not hit again inside the retry window"


# ----------------------------------------------------- fiscal rules fallback


class _Sql:
    def __init__(self, fails: bool):
        self.fails = fails

    def is_configured(self):
        return True

    def fiscal_year_rules(self, account_id):
        if self.fails:
            raise OSError("connection timed out")
        return ["from-sql"]


class _Delta:
    calls = 0

    def is_configured(self):
        return True

    def fiscal_year_rules(self, account_id):
        type(self).calls += 1
        return ["from-delta"]

    def for_account(self, account_id):
        raise AssertionError("the full Delta read was used")


@pytest.fixture
def fiscal(monkeypatch):
    from infrastructure.payroll import fiscal_source

    _Delta.calls = 0
    monkeypatch.setattr("data.source.from_fabric.FabricLakehouseReader", _Delta)
    return fiscal_source


def test_a_working_sql_path_is_used(fiscal, monkeypatch):
    monkeypatch.setattr("infrastructure.persistence.source_sql.SourceSqlReader", lambda: _Sql(False))
    assert fiscal._fiscal_rules(1) == ["from-sql"] and _Delta.calls == 0


def test_a_failing_sql_path_does_not_fall_through_to_another_store_by_default(fiscal, monkeypatch, caplog):
    monkeypatch.setattr("infrastructure.persistence.source_sql.SourceSqlReader", lambda: _Sql(True))
    monkeypatch.delenv("SOURCE_FALLBACK", raising=False)
    with caplog.at_level("WARNING"):
        assert fiscal._fiscal_rules(1) is None, "could not read: the caller assumes a flagged calendar year"
    assert _Delta.calls == 0
    assert "SOURCE_FALLBACK=delta" in caplog.text and "calendar year" in caplog.text


def test_the_delta_fallback_is_opt_in_bounded_and_logged(fiscal, monkeypatch, caplog):
    monkeypatch.setattr("infrastructure.persistence.source_sql.SourceSqlReader", lambda: _Sql(True))
    monkeypatch.setenv("SOURCE_FALLBACK", "delta")
    with caplog.at_level("WARNING"):
        assert fiscal._fiscal_rules(1) == ["from-delta"]
    assert _Delta.calls == 1 and "SOURCE_FALLBACK=delta" in caplog.text


def test_a_bug_in_the_sql_path_propagates(fiscal, monkeypatch):
    class Buggy(_Sql):
        def fiscal_year_rules(self, account_id):
            raise AttributeError("oops")

    monkeypatch.setattr("infrastructure.persistence.source_sql.SourceSqlReader", lambda: Buggy(False))
    with pytest.raises(AttributeError):
        fiscal._fiscal_rules(1)


def test_an_unknown_fallback_value_is_refused():
    from config import load_settings

    with pytest.raises(ValueError):
        load_settings({"SOURCE_FALLBACK": "sqlite"}).data_source
    assert load_settings({"SOURCE_FALLBACK": "none"}).data_source.source_fallback == ""


# ------------------------------------------------------------ classification


@pytest.mark.parametrize("error,fragment", [
    (RuntimeError("Invalid object name 'tcc_ops.x'"), "apply-migrations"),
    (RuntimeError("Login failed for user"), "grant"),
    (OSError("Login timeout expired"), "network"),
    (RuntimeError("something odd"), "log"),
])
def test_the_remedy_follows_the_kind_of_failure(error, fragment):
    failure = as_dependency_failure("claims_store", error)
    assert isinstance(failure, DependencyUnavailable) and fragment in failure.remedy.lower()


def test_the_reason_never_echoes_the_driver_message():
    failure = as_dependency_failure("claims_store", OSError("login failed for user 'svc-secret' on host-private.example"))
    assert "svc-secret" not in failure.reason and "host-private" not in failure.reason


@pytest.mark.parametrize("error", [TypeError("x"), AttributeError("x"), KeyError("x"), NameError("x")])
def test_programming_errors_are_not_classified(error):
    assert as_dependency_failure("claims_store", error) is None


# -------------------------------------------------------------- the probe


class _Migration:
    def __init__(self, version):
        self.version = version
        self.sha256 = "x"


@contextlib.contextmanager
def _live():
    yield object()


class _Conn:
    def require_configuration(self):
        pass

    def connect(self):
        return _live()


@pytest.fixture
def probe(monkeypatch):
    from infrastructure.persistence import schema_admin
    from infrastructure.persistence.store_probe import OperationalStoreProbe

    monkeypatch.setenv("CLAIM_STORE", "warehouse")
    state = {"applied": {"0000": "x"}, "tables": {"program_claim", "program_engagement"}}
    monkeypatch.setattr(schema_admin, "applied_migrations", lambda live, ops: state["applied"])
    monkeypatch.setattr(schema_admin, "table_exists", lambda live, schema, table: table in state["tables"])
    monkeypatch.setattr(OperationalStoreProbe, "_grants", lambda self, live: state.get("grants", []))
    return OperationalStoreProbe(_Conn()), state


def test_a_healthy_store_has_no_findings(probe):
    instance, _ = probe
    assert instance.probe([_Migration("0000")]) == []


def test_a_warehouse_never_bootstrapped_names_the_bootstrap(probe):
    instance, state = probe
    state["applied"] = None
    (finding,) = instance.probe()
    assert finding.code == "migration_table_missing" and "--bootstrap" in finding.remedy


def test_a_missing_claim_table_names_it_and_the_migration(probe):
    instance, state = probe
    state["tables"] = {"program_engagement"}
    (finding,) = instance.probe()
    assert "tcc_ops.program_claim not found" in finding.message and "run the migration" in finding.message


def test_pending_migrations_are_reported_with_the_first_version(probe):
    instance, state = probe
    (finding,) = instance.probe([_Migration("0000"), _Migration("0003")])
    assert finding.code == "migrations_pending" and "0003" in finding.message


def test_an_unreachable_server_is_a_finding_with_a_network_remedy(probe, monkeypatch):
    instance, _ = probe

    @contextlib.contextmanager
    def refuse():
        raise OSError("Login timeout expired")
        yield

    monkeypatch.setattr(instance._connection, "connect", refuse, raising=False)
    (finding,) = instance.probe()
    assert finding.code == "operational_store_unreachable" and "network" in finding.remedy.lower()


def test_a_local_store_needs_no_check(monkeypatch):
    from infrastructure.persistence.store_probe import OperationalStoreProbe

    monkeypatch.setenv("CLAIM_STORE", "sqlite")
    assert OperationalStoreProbe(_Conn()).probe() == []


# ------------------------------------------------------- settings warnings


def test_a_placeholder_host_and_mixed_stores_are_warned_about():
    from application.store_readiness import settings_findings

    codes = {f.code for f in settings_findings({
        "WAREHOUSE_SERVER": "<id>.datawarehouse.example.net", "WAREHOUSE_DATABASE": "wh", "CLAIM_STORE": "sqlite",
        "ENVIRONMENT": "local",
    })}
    assert codes == {"placeholder_setting", "mixed_store_settings"}
    assert settings_findings({"ENVIRONMENT": "local"}) == []


def test_the_report_says_degraded_only_for_a_problem(monkeypatch):
    from application import store_readiness
    from application.store_readiness import Finding

    class Probe:
        def __init__(self, findings):
            self.findings = findings

        def probe(self, migrations=None):
            return self.findings

    monkeypatch.setattr("application.services.get_store_probe", lambda: Probe([Finding("w", "m", "r", "warning")]))
    assert store_readiness.check_operational_store()["status"] == "ready"
    monkeypatch.setattr("application.services.get_store_probe", lambda: Probe([Finding("p", "m", "r")]))
    report = store_readiness.check_operational_store()
    assert report["status"] == "degraded" and report["problems"][0]["remedy"] == "r"


def test_the_readiness_endpoint_reports_the_stores_without_failing_the_probe(monkeypatch):
    from main import app

    app.state.stores = {"status": "degraded", "problems": [{"code": "x", "message": "m", "remedy": "r", "severity": "problem"}], "warnings": []}
    app.state.started = True
    body = TestClient(app).get("/api/ready").json()
    assert body["stores"]["status"] == "degraded"
    assert body["ready"] is True, "a store problem is reported, not a reason for the platform to restart the app"
    app.state.started = False
