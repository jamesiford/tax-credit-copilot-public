"""Per-caller limits on draft save, preview, export and batch start. [F07.3]"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application import request_limits
from tests import draft_world as dw
from tests.test_agent_principal import acting_header, entra  # noqa: F401 - fixture
from tests.test_auth import mint

BASE = "/api/v2/program-drafts"


def test_each_kind_and_each_caller_has_its_own_bucket():
    request_limits.reset()
    bucket = request_limits._limiter(2)
    assert [bucket.allow("draft_save:a")[0] for _ in range(3)] == [True, True, False]
    assert bucket.allow("draft_save:b")[0] is True, "another caller has its own allowance"
    assert bucket.allow("draft_export:a")[0] is True, "each kind is counted on its own"
    assert request_limits._limiter(2) is bucket and request_limits._limiter(5) is not bucket


@pytest.fixture()
def api(monkeypatch):
    import main
    from bootstrap import program_draft_wiring
    from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository

    repo = SqliteProgramDraftRepository(":memory:")
    program_draft_wiring.set_program_draft_repository(repo)
    request_limits.reset()
    yield TestClient(main.app)
    request_limits.reset()
    program_draft_wiring.set_program_draft_repository(None)
    repo.close()


def _signed_in():
    return {"Authorization": f"Bearer {mint()}"}


def _draft(api, headers):
    return api.post(BASE, headers=headers, json={"code": dw.CODE, "name": "x", "state": dw.STATE, "years": []}).json()


def test_a_signed_in_caller_past_the_limit_gets_a_429_with_retry_after_a_code_and_a_remedy(entra, api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    headers = _signed_in()
    draft = _draft(api, headers)
    body = {"expected_version": draft["version"], "pack": draft["documents"]["pack"], "years": draft["documents"]["years"]}
    codes = [api.put(f"{BASE}/{draft['draft_id']}/documents", headers=headers, json=body).status_code for _ in range(4)]
    assert codes[:3] != [429] * 3 and codes[3] == 429
    refused = api.put(f"{BASE}/{draft['draft_id']}/documents", headers=headers, json=body)
    assert refused.status_code == 429 and int(refused.headers["retry-after"]) >= 1
    assert refused.json()["detail"]["code"] == "rate_limited" and "RATE_LIMIT_PER_MINUTE" in refused.json()["detail"]["remedy"]
    assert api.post(f"{BASE}/{draft['draft_id']}/preview", headers=headers, json={}).status_code != 429, "preview has its own count"


def test_preview_export_and_batch_start_are_limited_too(entra, api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    headers = _signed_in()
    draft = _draft(api, headers)
    for path in (f"{BASE}/{draft['draft_id']}/preview", f"{BASE}/{draft['draft_id']}/export", "/api/v2/run-batches"):
        first = api.post(path, headers=headers, json={})
        second = api.post(path, headers=headers, json={})
        assert first.status_code != 429 and second.status_code == 429, path


def test_nobody_signed_in_is_never_limited(api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    draft = api.post(BASE, json={"code": dw.CODE, "name": "x", "state": dw.STATE, "actor": "ann"}).json()
    assert all(api.post(f"{BASE}/{draft['draft_id']}/preview", json={}).status_code != 429 for _ in range(5))


def test_zero_turns_the_limit_off_and_the_default_is_sixty(entra, api, monkeypatch):
    from config import load_settings

    assert load_settings({}).limits.per_minute == 60
    assert load_settings({"RATE_LIMIT_PER_MINUTE": "0"}).limits.per_minute == 0
    assert load_settings({"RATE_LIMIT_PER_MINUTE": "junk"}).limits.per_minute == 60
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    headers = _signed_in()
    draft = _draft(api, headers)
    assert all(api.post(f"{BASE}/{draft['draft_id']}/preview", headers=headers, json={}).status_code != 429 for _ in range(8))
