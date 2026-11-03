"""`POST /channel/v1/audit/narration`: a model's involvement, on the record per user. [CH-08]"""
from __future__ import annotations

import hashlib

from gateway_harness import USER_OID, agent_headers, build_gateway, user_headers

URL = "/channel/v1/audit/narration"
PROMPT_SHA = hashlib.sha256(b"a prompt").hexdigest()


def report(**over):
    body = {
        "agent_name": "ChannelNarratorAgent", "agent_version": "3", "model": "narrator-deployment",
        "prompt_sha256": PROMPT_SHA, "tool_names": ["client_eligibility", "client_trend"],
        "guard_status": "pass", "violations_count": 0, "output_summary": "blocks=3; chars=420",
    }
    return {**body, **over}


def test_a_passed_narration_writes_both_rows_as_deterministic(gateway):
    reply = gateway.client.post(URL, json=report(), headers=agent_headers())
    assert reply.status_code == 200 and reply.json()["agent_action_recorded"] is True
    (event,) = [e for e in gateway.events() if e.action_kind == "narrate"]
    assert (event.numeric_guard, event.outcome, event.is_deterministic_path) == ("pass", "ok", True)
    assert event.user_oid == USER_OID and event.conversation_id == "conv-1" and event.correlation_id == "corr-1"
    (row,) = gateway.actions.recent()
    assert row.is_deterministic_path is True and row.prompt_hash == PROMPT_SHA
    assert row.agent_name == "ChannelNarratorAgent" and row.model_deployment == "narrator-deployment"
    assert "client_trend" in row.tool_calls and row.user_upn == USER_OID


def test_a_rejected_narration_is_not_deterministic_and_says_how_many_figures_failed(gateway):
    gateway.client.post(URL, json=report(guard_status="rejected", violations_count=2), headers=agent_headers())
    (event,) = [e for e in gateway.events() if e.action_kind == "narrate"]
    assert (event.numeric_guard, event.outcome, event.is_deterministic_path) == ("rejected", "rejected_by_guard", False)
    assert "2 figure" in event.error
    assert gateway.actions.recent()[0].is_deterministic_path is False


def test_the_record_holds_a_hash_and_a_note_never_the_prompt_or_the_reply(gateway):
    gateway.client.post(URL, json=report(), headers=agent_headers())
    (event,) = [e for e in gateway.events() if e.action_kind == "narrate"]
    assert PROMPT_SHA in (event.request_summary or "") or event.request_sha256
    assert "a prompt" not in (event.request_summary or "")


def test_a_malformed_report_is_refused_and_writes_nothing(gateway):
    for bad in (report(prompt_sha256="nope"), report(guard_status="maybe"), report(violations_count=-1),
                report(guard_status="pass", violations_count=1), {**report(), "extra": 1}, {}):
        assert gateway.client.post(URL, json=bad, headers=agent_headers()).status_code == 422
    assert gateway.events() == [] and gateway.actions.recent() == []


def test_only_an_agent_caller_may_report_and_it_must_be_authenticated(gateway):
    assert gateway.client.post(URL, json=report()).status_code == 401
    assert gateway.client.post(URL, json=report(), headers=user_headers()).status_code == 403
    assert gateway.events() == []


def test_a_failing_trail_is_a_503_not_a_silent_success(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api)

    def boom(*_a, **_k):
        raise RuntimeError("store down")

    gw.audit.append = boom
    reply = gw.client.post(URL, json=report(), headers=agent_headers())
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "audit_unavailable"
