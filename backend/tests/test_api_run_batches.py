"""The run batch API: contract, refusals with remedies, and who may call it.

Offline: a private SQLite queue and a stubbed client book. The worker is not started, so batches stay queued, which is
what these tests need; execution is covered by test_run_orchestration.py and test_run_batches_end_to_end.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application.runs import selection
from tests.test_agent_principal import _agent, acting_header, entra  # noqa: F401 - fixture

BOOK = [{"account_id": i, "name": f"Client {i}"} for i in range(1, 6)]


@pytest.fixture()
def api(monkeypatch):
    import main
    from bootstrap import run_batch_wiring
    from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

    repo = SqliteRunBatchRepository(":memory:")
    run_batch_wiring.set_run_batch_repository(repo)
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr("application.runs.plan._assumptions", lambda: [])
    monkeypatch.setattr("application.services.get_run_manifest_repository", lambda: type("M", (), {"latest": lambda s, c, **k: None})())
    monkeypatch.setenv("RUN_BATCH_CONFIRM_ABOVE", "3")
    yield TestClient(main.app)
    run_batch_wiring.set_run_batch_repository(None)
    repo.close()


def _start(api, **body):
    body.setdefault("scope", {"kind": "list", "client_ids": [1, 2]})
    return api.post("/api/v2/run-batches", json=body)


def test_start_queues_a_batch_and_returns_it_without_waiting(api):
    r = _start(api, idempotency_key="k1")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["counts"]["total"] == 2 and body["progress"] == {"done": 0, "total": 2}
    assert body["idempotent_replay"] is False
    got = api.get(f"/api/v2/run-batches/{body['batch_id']}").json()
    assert got["batch_id"] == body["batch_id"] and got["degraded"] == []


def test_dry_run_writes_nothing_and_says_it_is_a_preview(api):
    r = _start(api, dry_run=True, scope={"kind": "all"})
    assert r.status_code == 202 and r.json()["dry_run"] is True
    preview = r.json()["preview"]
    assert preview["clients"] == 5 and preview["requires_confirmation"] is True
    assert any("upper bound" in n for n in preview["notes"])
    assert api.get("/api/v2/run-batches").json()["total"] == 0


def test_the_same_key_returns_the_same_batch(api):
    a = _start(api, idempotency_key="same").json()
    b = _start(api, idempotency_key="same", scope={"kind": "list", "client_ids": [3]}).json()
    assert b["batch_id"] == a["batch_id"] and b["idempotent_replay"] is True


def test_refusals_carry_a_code_a_reason_and_a_remedy(api):
    needs = _start(api, scope={"kind": "all"})
    assert needs.status_code == 409
    detail = needs.json()["detail"]
    assert detail["code"] == "confirmation_required" and "confirm_items=5" in detail["remedy"]
    assert _start(api, scope={"kind": "all"}, confirm_items=5).status_code == 202
    unknown = _start(api, scope={"kind": "list", "client_ids": [1, 999]})
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "unknown_clients"
    empty = _start(api, scope={"kind": "list", "client_ids": []})
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "empty_scope"
    assert _start(api, refresh_once=False).status_code == 422


def test_a_body_that_is_not_the_contract_is_a_422(api):
    assert api.post("/api/v2/run-batches", json={"scope": {"kind": "everyone"}}).status_code == 422
    assert api.post("/api/v2/run-batches", json={"kind": "calculate"}).status_code == 422


def test_list_items_cancel_and_retry(api):
    batch = _start(api, scope={"kind": "list", "client_ids": [1, 2, 3]}).json()
    bid = batch["batch_id"]
    page = api.get(f"/api/v2/run-batches/{bid}/items", params={"limit": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["items"][0]["status"] == "queued"
    assert api.get(f"/api/v2/run-batches/{bid}/items", params={"status": "failed"}).json()["total"] == 0
    cancelled = api.post(f"/api/v2/run-batches/{bid}/cancel").json()
    assert cancelled["cancelled_now"] == 3 and cancelled["status"] == "cancelled" and cancelled["counts"]["cancelled"] == 3
    again = api.post(f"/api/v2/run-batches/{bid}/retry-failed").json()
    assert again["requeued"] == 0
    listing = api.get("/api/v2/run-batches", params={"status": "cancelled"}).json()
    assert listing["total"] == 1 and listing["items"][0]["batch_id"] == bid


def test_an_unknown_batch_is_a_404_everywhere(api):
    for call in (lambda: api.get("/api/v2/run-batches/nope"), lambda: api.get("/api/v2/run-batches/nope/items"),
                 lambda: api.post("/api/v2/run-batches/nope/cancel"), lambda: api.post("/api/v2/run-batches/nope/retry-failed")):
        assert call().status_code == 404


def test_the_requester_is_the_authenticated_person_not_the_body(api):
    assert _start(api).json()["requested_by"] == "anonymous"


def test_an_agent_token_is_refused_on_every_write_route_and_may_read(entra, api):  # noqa: F811
    header = _agent(acting_header())
    assert api.post("/api/v2/run-batches", headers=header, json={"scope": {"kind": "all"}}).status_code == 403
    assert api.post("/api/v2/run-batches/x/cancel", headers=header).status_code == 403
    assert api.post("/api/v2/run-batches/x/retry-failed", headers=header).status_code == 403
    assert api.get("/api/v2/run-batches", headers=header).status_code == 200
