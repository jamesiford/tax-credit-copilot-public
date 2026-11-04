"""The hosting shell's decisions, with plain objects standing in for the Responses context. [CH-08]"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.core.state import StateStore
from app.host import answer, conversation_of, signals_of, who_is_asking
from app.wiring import Orchestrator
from orch_harness import TENANT, USER_OID, build_rig


def context(headers=None, subject=None, user_id_key=None, conversation_id="conv-1", chain="chain-1", response_id="resp_1"):
    return SimpleNamespace(
        client_headers=headers or {}, platform_context=SimpleNamespace(original_subject=subject, user_id_key=user_id_key),
        conversation_id=conversation_id, conversation_chain_id=chain, response_id=response_id,
    )


def orchestrator(script=None, **env) -> tuple[Orchestrator, object]:
    rig = build_rig(script or [], env=env)
    return Orchestrator(rig.settings, rig.pipeline, rig.pipeline._planner._chain, rig.pipeline._gateway), rig


def run(orch, ctx, text):
    return asyncio.run(answer(orch, ctx, text))


def test_the_original_subject_the_platform_sends_becomes_the_acting_user():
    orch, rig = orchestrator([{"tools": [{"tool": "book_rank", "args": {}}]}, {"text": "The table ranks them."}])
    subject = SimpleNamespace(oid=USER_OID, tid=TENANT, idtype="user")
    text = run(orch, context(subject=subject), "Who should we call first?")
    assert "Who to call" in text
    assert rig.gateway.calls[0].headers["x-acting-user-oid"] == USER_OID


def test_no_signal_means_a_refusal_and_not_a_single_call():
    orch, rig = orchestrator([{"text": "never"}])
    text = run(orch, context(user_id_key="opaque-only"), "Who should we call first?")
    assert "can't tell who you are" in text and rig.gateway.calls == [] and rig.chat.seen == []


def test_the_conversation_falls_back_to_the_response_chain():
    assert conversation_of(context(conversation_id=None)) == "chain-1"
    assert conversation_of(context(conversation_id="c")) == "c"


def test_the_signals_are_lowercased_and_the_opaque_id_is_carried_but_never_trusted():
    signals = signals_of(context(headers={"X-Client-Tenant": TENANT}, user_id_key="opaque"))
    assert signals["x-client-tenant"] == TENANT and signals["x-agent-user-id"] == "opaque"


def test_whoami_is_inert_unless_switched_on():
    orch, _ = orchestrator([{"text": "never"}])
    text = run(orch, context(), "/whoami")
    assert "can't tell who you are" in text and "signals" not in text


def test_whoami_reports_signals_and_the_resolution_when_switched_on_and_leaks_no_credential():
    orch, _ = orchestrator(CHANNEL_DEBUG_WHOAMI="true", CHANNEL_IDENTITY_SOURCES="client-headers")
    ctx = context(headers={"x-client-acting-user-oid": USER_OID, "Authorization": "Bearer secret-token", "cookie": "a=b"})
    text = run(orch, ctx, "/whoami")
    report = json.loads(text)
    assert report["identity"]["source"] == "client-headers" and report["identity"]["oid"] == USER_OID
    assert "secret-token" not in text and "cookie" not in text
    assert report["turns"]["audit_failures"] == 0 and report["sources"] == ["client-headers"]


def test_whoami_with_no_identity_says_why_which_is_the_point_of_the_spike():
    orch, _ = orchestrator(CHANNEL_DEBUG_WHOAMI="true")
    report = json.loads(run(orch, context(headers={"x-agent-user-id": "opaque"}), "/whoami"))
    assert report["identity"]["resolved"] is False and "no configured source" in report["identity"]["reason"]
    assert report["signals"]["present"] == ["x-agent-user-id"]


def test_whoami_names_the_person_the_channel_and_the_conversation():
    orch, _ = orchestrator(CHANNEL_DEBUG_WHOAMI="true", CHANNEL_IDENTITY_SOURCES="client-headers")
    ctx = context(headers={"x-client-acting-user-oid": USER_OID, "x-client-acting-user-name": "Pat Writer"})
    identity = json.loads(run(orch, ctx, "/whoami"))["identity"]
    assert identity == {"resolved": True, "source": "client-headers", "oid": USER_OID, "tenant": TENANT,
                        "display_name": "Pat Writer", "channel": "teams", "conversation": "conv-1"}


def test_a_refused_turn_shows_what_was_received_only_when_debugging():
    quiet, _ = orchestrator([{"text": "never"}])
    assert "signals" not in run(quiet, context(headers={"x-agent-user-id": "opaque"}), "Who should we call?")
    debug, _ = orchestrator(CHANNEL_DEBUG_WHOAMI="true")
    text = run(debug, context(headers={"x-agent-user-id": "opaque", "authorization": "Bearer secret-token"}), "Who should we call?")
    assert "can't tell who you are" in text and '"present"' in text and "x-agent-user-id" in text
    assert "secret-token" not in text


def test_a_correlation_id_is_made_safe_for_the_gateway():
    orch, _ = orchestrator()
    who = who_is_asking(orch, context(headers={"x-client-acting-user-oid": USER_OID}, response_id="resp/ bad:id"))
    assert getattr(who, "reason", "").startswith("no configured source")
    orch2, _ = orchestrator(CHANNEL_IDENTITY_SOURCES="client-headers")
    who = who_is_asking(orch2, context(headers={"x-client-acting-user-oid": USER_OID}, response_id="resp/ bad:id"))
    assert who.correlation_id == "respbadid" and StateStore
