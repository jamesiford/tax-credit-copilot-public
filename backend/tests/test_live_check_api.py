"""The scripted live checks, proved against the in-process app. [F07.6]"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_agent_principal import entra  # noqa: F401 - fixture
from tests.test_auth import mint

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "live-check-api.py"


@pytest.fixture(scope="module")
def checks():
    spec = importlib.util.spec_from_file_location("live_check_api", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["live_check_api"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def api():
    import main
    from api import _rate_limit  # noqa: F401 - imported so the route table is built
    from application import request_limits
    from bootstrap import program_draft_wiring, run_batch_wiring
    from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository
    from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

    drafts, batches = SqliteProgramDraftRepository(":memory:"), SqliteRunBatchRepository(":memory:")
    program_draft_wiring.set_program_draft_repository(drafts)
    run_batch_wiring.set_run_batch_repository(batches)
    request_limits.reset()
    yield TestClient(main.app)
    request_limits.reset()
    program_draft_wiring.set_program_draft_repository(None)
    run_batch_wiring.set_run_batch_repository(None)
    drafts.close()
    batches.close()


def test_the_bounds_check_sees_four_refusals_and_writes_nothing(checks, api):
    report = checks.check_bounds(api)
    assert [o.name for o in report.outcomes] == [
        "draft name of 201 characters", "review comment of 2001 characters", "batch filter value of 65 characters", "tax_years of 13 years"]
    assert not report.failures, checks.render(report)
    assert api.get(checks.DRAFTS).json()["total"] == 0


def test_the_bounds_check_with_writes_accepts_the_limit_then_withdraws_its_draft(checks, api):
    report = checks.check_bounds(api, allow_writes=True)
    assert not report.failures, checks.render(report)
    listed = api.get(checks.DRAFTS).json()
    assert listed["total"] == 1 and listed["items"][0]["status"] == "withdrawn"


def test_the_bounds_check_fails_loudly_when_a_limit_is_not_enforced(checks):
    import httpx

    lax = httpx.Client(base_url="http://x", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    report = checks.check_bounds(lax)
    assert len(report.failures) == 4 and "FAIL" in checks.render(report)


def test_the_rate_limit_check_trips_at_the_limit_for_a_signed_in_caller(checks, entra, api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    api.headers["Authorization"] = f"Bearer {mint()}"
    report = checks.check_rate_limit(api, limit=3)
    assert not report.failures, checks.render(report)


def test_the_rate_limit_check_reports_a_sandbox_with_the_limit_off(checks, entra, api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    api.headers["Authorization"] = f"Bearer {mint()}"
    report = checks.check_rate_limit(api, limit=3)
    assert [o.name for o in report.failures] == ["the next request is a 429", "it says when to retry"]


def test_the_guard_is_the_smoke_scripts_and_refuses_production_and_unknown_targets(checks, monkeypatch, capsys):
    monkeypatch.setenv("SMOKE_TARGETS", "prod-eu=https://p.example")
    assert checks.main(["--target", "prod-eu", "bounds"]) == checks.EXIT_GUARD
    assert checks.main(["--target", "nowhere", "rate-limit"]) == checks.EXIT_GUARD
    assert "GUARD REFUSED" in capsys.readouterr().err
