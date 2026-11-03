"""One call through the gateway: audited, bounded, forwarded as the person. [CH-06]

Against a fake API: what the gateway sends (the managed-identity token, the acting-user
header, the correlation id), what it writes to the trail (a read: begin and end, always;
a write: one event only for what the capability could not see), and what it refuses
before the API is bothered.
"""
from __future__ import annotations

import json

import httpx
import pytest

from api.auth import AGENT_FORBIDDEN_WRITES
from application.capabilities import catalog
from channel.tools import offered_tools
from gateway_harness import (
    OTHER_OID, TENANT, USER_OID, FakeApi, agent_headers, build_gateway, envelope, user_headers,
)

CALL = "/channel/v1/tools/client_situation"
ARGS = {"args": {"client_id": 2001}}
WRITE = {"args": {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope"}}


def shape(events):
    return [(e.tool_name, e.phase, e.outcome, e.action_kind) for e in events]


# ---------------------------------------------------------------------- reads


def test_a_read_returns_the_apis_envelope_unchanged_plus_the_correlation_id(gateway, fake_api):
    body = gateway.client.post(CALL, json=ARGS, headers=agent_headers()).json()
    assert body.pop("correlation_id") == "corr-1"
    assert body == envelope("client_situation")


def test_a_read_writes_a_begin_and_an_end_with_the_run_and_trail(gateway):
    gateway.client.post(CALL, json=ARGS, headers=agent_headers())
    events = gateway.events()
    assert shape(events) == [("client_situation", "begin", "pending", "read"), ("client_situation", "end", "ok", "read")]
    begin, end = events
    assert begin.audit_id == end.audit_id and {e.correlation_id for e in events} == {"corr-1"}
    assert (end.run_id, end.trail_sha256) == ("run-1", "ab" * 32) and end.numeric_guard == "n/a"
    assert begin.request_sha256 and begin.client_id == 2001
    assert {e.identity_assurance for e in events} == {"channel-asserted"} and {e.channel for e in events} == {"teams"}
    assert end.elapsed_ms is not None and begin.request_summary == "client_id=2001"


def test_the_api_is_called_as_the_gateway_for_the_named_person(gateway, fake_api):
    gateway.client.post(CALL, json=ARGS, headers=agent_headers())
    [call] = fake_api.calls
    assert call["authorization"] == "Bearer api-token" and call["correlation"] == "corr-1"
    acting = call["acting"]
    assert (acting.oid, acting.tenant_id, acting.display_name) == (USER_OID, TENANT, "Pat Writer")
    assert (acting.channel, acting.conversation_id, acting.correlation_id, acting.assurance) == (
        "teams", "conv-1", "corr-1", "channel-asserted")
    assert call["body"] == {"args": {"client_id": 2001}}


def test_a_delegated_call_is_forwarded_as_delegated(gateway, fake_api):
    gateway.client.post(CALL, json=ARGS, headers=user_headers())
    acting = fake_api.calls[0]["acting"]
    assert (acting.oid, acting.channel, acting.assurance, acting.upn) == (USER_OID, "cowork", "delegated", "pat@example.com")


@pytest.mark.parametrize(
    "status, code, outcome",
    [(409, "not_calculated", "error"), (404, "client_not_found", "error"), (403, "not_authorized", "refused"),
     (422, "year_not_authored", "error")],
)
def test_an_api_refusal_passes_through_and_closes_the_trail(gateway, fake_api, status, code, outcome):
    fake_api.replies["client_situation"] = (status, {"error": {"code": code, "message": "no", "retryable": False}})
    response = gateway.client.post(CALL, json=ARGS, headers=agent_headers())
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert response.json()["correlation_id"] == "corr-1"
    assert shape(gateway.events())[-1] == ("client_situation", "end", outcome, "read")
    assert code in gateway.events()[-1].error


def test_a_slow_api_is_a_504_and_the_trail_still_closes(tmp_path):
    def too_slow(request):
        raise httpx.ReadTimeout("slow")

    gw = build_gateway(tmp_path, transport=httpx.MockTransport(too_slow))
    response = gw.client.post(CALL, json=ARGS, headers=agent_headers())
    assert response.status_code == 504 and response.json()["error"] == {
        "code": "timeout", "message": "the API did not answer in time", "retryable": True}
    assert shape(gw.events())[-1][1:3] == ("end", "error")


def test_an_unreachable_api_is_a_502_and_the_trail_closes(tmp_path):
    def refuse(request):
        raise httpx.ConnectError("no route")

    gw = build_gateway(tmp_path, transport=httpx.MockTransport(refuse))
    response = gw.client.post(CALL, json=ARGS, headers=agent_headers())
    assert response.status_code == 502 and response.json()["error"]["code"] == "api_unreachable"
    assert shape(gw.events())[-1][1:3] == ("end", "error")


def test_the_apis_guard_refusing_the_gateway_is_a_502_not_a_403(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(403, json={"detail": "token lacks the 'TCC.Agent' app role"}))
    gw = build_gateway(tmp_path, transport=transport)
    response = gw.client.post(CALL, json=ARGS, headers=agent_headers())
    assert response.status_code == 502 and response.json()["error"]["code"] == "api_error"
    assert "TCC.Agent" not in response.text


def test_an_unknown_tool_is_a_404_and_the_api_is_not_called(gateway, fake_api):
    response = gateway.client.post("/channel/v1/tools/drop_tables", json={}, headers=agent_headers())
    assert response.status_code == 404 and response.json()["error"]["code"] == "unknown_tool"
    assert fake_api.calls == [] and gateway.events() == []


def test_the_plumbing_tool_is_not_a_tool_a_caller_can_name(gateway, fake_api):
    response = gateway.client.post("/channel/v1/tools/claim_package_redeem", json={"args": {"ticket": "t" * 20}}, headers=agent_headers())
    assert response.status_code == 404 and fake_api.calls == []


def test_the_tool_list_is_the_offered_catalog_and_hides_the_plumbing(gateway):
    tools = gateway.client.get("/channel/v1/tools", headers=agent_headers()).json()["tools"]
    assert {t["name"] for t in tools} == {s.name for s in catalog.offered()}
    assert "claim_package_redeem" not in {t["name"] for t in tools}


# ---------------------------------------------------------------- the audit gate


def test_when_the_opening_event_cannot_be_written_nothing_is_called(gateway, fake_api, monkeypatch):
    def fail(event):
        raise RuntimeError("warehouse down")

    monkeypatch.setattr(gateway.audit, "append", fail)
    response = gateway.client.post(CALL, json=ARGS, headers=agent_headers())
    assert response.status_code == 503 and response.json()["error"]["code"] == "audit_unavailable"
    assert fake_api.calls == []


# ---------------------------------------------------------------- rate limiting


def test_the_per_user_rate_limit_is_a_retryable_429_and_is_itself_audited(tmp_path):
    api = FakeApi()
    gw = build_gateway(tmp_path, api=api, rate_limit_per_minute=2)
    for _ in range(2):
        assert gw.client.post(CALL, json=ARGS, headers=agent_headers()).status_code == 200
    blocked = gw.client.post(CALL, json=ARGS, headers=agent_headers())
    assert blocked.status_code == 429 and blocked.json()["error"]["retryable"] is True
    assert int(blocked.headers["retry-after"]) >= 1 and blocked.json()["error"]["retry_after_seconds"] >= 1
    assert len(api.calls) == 2
    last = gw.events()[-1]
    assert (last.phase, last.outcome, last.error) == ("single", "refused", "rate_limited")
    gw.clock.now += 60
    assert gw.client.post(CALL, json=ARGS, headers=agent_headers()).status_code == 200


def test_the_limit_is_per_user(tmp_path):
    gw = build_gateway(tmp_path, rate_limit_per_minute=1)
    assert gw.client.post(CALL, json=ARGS, headers=agent_headers()).status_code == 200
    assert gw.client.post(CALL, json=ARGS, headers=agent_headers()).status_code == 429
    assert gw.client.post(CALL, json=ARGS, headers=agent_headers(oid=OTHER_OID)).status_code == 200


# -------------------------------------------------------------------- the caps


def test_a_body_over_the_cap_is_a_413_before_anything_is_read_or_called(gateway, fake_api):
    big = {"args": {"client_id": 1, "x": "y" * 70_000}}
    response = gateway.client.post(CALL, json=big, headers=agent_headers())
    assert response.status_code == 413 and response.json()["error"]["code"] == "request_too_large"
    assert fake_api.calls == []


def test_a_response_over_the_cap_is_a_502_not_a_buffer(gateway, fake_api):
    fake_api.replies["client_situation"] = (200, {"facts": {"blob": "x" * 1_100_000}})
    response = gateway.client.post(CALL, json=ARGS, headers=agent_headers())
    assert response.status_code == 502 and response.json()["error"]["code"] == "bad_response"
    assert shape(gateway.events())[-1][1:3] == ("end", "error")


@pytest.mark.parametrize("raw", ["not json", '{"args": []}', '{"args": {}, "idempotency_key": 5}'])
def test_a_malformed_body_is_a_422(gateway, raw):
    response = gateway.client.post(CALL, content=raw, headers={**agent_headers(), "Content-Type": "application/json"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


# ----------------------------------------------------------------------- writes


def test_a_commit_by_somebody_who_may_not_write_is_refused_at_the_gateway(gateway, fake_api):
    response = gateway.client.post(
        "/channel/v1/tools/engagement_set_commit", json=WRITE, headers=agent_headers(oid=OTHER_OID))
    assert response.status_code == 403 and response.json()["error"]["code"] == "not_authorized"
    assert fake_api.calls == []
    [event] = gateway.events(OTHER_OID)
    assert (event.tool_name, event.action_kind, event.phase, event.outcome) == (
        "engagement_set_commit", "write_commit", "single", "refused")
    assert event.correlation_id == "corr-1"


def test_a_broken_entitlement_source_denies(tmp_path):
    gw = build_gateway(tmp_path)

    class Broken:
        def is_writer(self, oid):
            raise RuntimeError("graph is down")

    gw.services.pipeline._entitlement = Broken()
    assert gw.client.post("/channel/v1/tools/engagement_set_commit", json=WRITE, headers=agent_headers()).status_code == 403


def test_a_prepare_is_not_gated_at_the_gateway_the_api_decides(gateway, fake_api):
    gateway.client.post("/channel/v1/tools/engagement_set_prepare", json=WRITE, headers=agent_headers(oid=OTHER_OID))
    assert [c["tool"] for c in fake_api.calls] == ["engagement_set_prepare"]


def test_a_successful_write_adds_no_gateway_event_the_capability_audits_itself(gateway, fake_api):
    for step in ("prepare", "commit"):
        assert gateway.client.post(f"/channel/v1/tools/engagement_set_{step}", json=WRITE, headers=agent_headers()).status_code == 200
    assert gateway.events() == []
    assert [c["tool"] for c in fake_api.calls] == ["engagement_set_prepare", "engagement_set_commit"]


def test_a_write_the_capability_refused_is_not_audited_twice(gateway, fake_api):
    fake_api.replies["engagement_set_commit"] = (409, {"error": {"code": "confirmation_replayed", "message": "used", "retryable": False}})
    response = gateway.client.post("/channel/v1/tools/engagement_set_commit", json=WRITE, headers=agent_headers())
    assert response.status_code == 409 and gateway.events() == []


@pytest.mark.parametrize(
    "status, code, outcome",
    [(422, "invalid_arguments", "error"), (403, "client_not_authorized", "refused"), (504, "timeout", "error")],
)
def test_a_write_that_failed_before_the_capability_ran_has_one_explaining_event(gateway, fake_api, status, code, outcome):
    fake_api.replies["engagement_set_prepare"] = (status, {"error": {"code": code, "message": "no", "retryable": False}})
    gateway.client.post("/channel/v1/tools/engagement_set_prepare", json=WRITE, headers=agent_headers())
    [event] = gateway.events()
    assert (event.phase, event.outcome, event.action_kind, event.correlation_id) == ("single", outcome, "write_prepare", "corr-1")
    assert code in event.error


def test_an_unreachable_api_on_a_write_has_one_explaining_event(tmp_path):
    def refuse(request):
        raise httpx.ConnectError("no route")

    gw = build_gateway(tmp_path, transport=httpx.MockTransport(refuse))
    gw.client.post("/channel/v1/tools/engagement_set_commit", json=WRITE, headers=agent_headers())
    [event] = gw.events()
    assert (event.phase, event.outcome) == ("single", "error") and "api_unreachable" in event.error


def test_a_commit_forwards_its_token_and_key_for_the_api_to_check(gateway, fake_api):
    body = {**WRITE, "confirmation_token": "tok-" + "a" * 20, "idempotency_key": "idem-1"}
    gateway.client.post("/channel/v1/tools/engagement_set_commit", json=body, headers=agent_headers())
    assert fake_api.calls[0]["body"] == {"args": WRITE["args"], "confirmation_token": "tok-" + "a" * 20, "idempotency_key": "idem-1"}


def test_the_trail_never_holds_the_confirmation_token(gateway, fake_api):
    token = "tok-" + "z" * 30
    fake_api.replies["engagement_set_commit"] = (422, {"error": {"code": "invalid_arguments", "message": "x", "retryable": False}})
    gateway.client.post("/channel/v1/tools/engagement_set_commit", json={**WRITE, "confirmation_token": token}, headers=agent_headers())
    dump = json.dumps([e.to_dict() for e in gateway.events()])
    assert token not in dump


# --------------------------------------------------------- the surface it routes to


def test_the_gateway_only_ever_calls_the_capability_endpoint_health_and_artifacts(tmp_path):
    api = FakeApi()
    gw = build_gateway(tmp_path, api=api, debug_whoami=True, writers={USER_OID})
    for spec in offered_tools(gw.services.settings):
        gw.client.post(f"/channel/v1/tools/{spec.name}", json={"args": {}}, headers=agent_headers())
    assert api.paths, "the sweep reached the API"
    allowed = ("/api/capabilities/", "/api/health", "/api/clients/")
    assert all(p.startswith(allowed) for p in api.paths)
    method_paths = [f"POST {p}" for p in api.paths] + [f"GET {p}" for p in api.paths]
    assert not any(rx.match(mp) for rx in AGENT_FORBIDDEN_WRITES for mp in method_paths)
