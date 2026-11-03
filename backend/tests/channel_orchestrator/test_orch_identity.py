"""Who is asking: resolved from platform signals, or nothing runs. [CH-08]"""
from __future__ import annotations

import asyncio
import json

from app.core.identity import ActingIdentity, Refusal, describe_signals, resolve_identity
from orch_harness import OTHER_OID, TENANT, USER_OID, build_rig

CONVERSATION = "conv-9"


def resolve(signals, sources=("original-subject", "platform"), conversation=CONVERSATION):
    return resolve_identity(signals, sources=sources, tenant_id=TENANT, channel="teams",
                            conversation_id=conversation, correlation_id="corr-1")


def test_the_original_subject_is_the_first_source_and_is_recorded_as_such():
    who = resolve({"x-ms-original-subject-oid": USER_OID.upper(), "x-ms-original-subject-tid": TENANT, "x-ms-user-identity": OTHER_OID})
    assert isinstance(who, ActingIdentity) and who.oid == USER_OID and who.source == "original-subject"


def test_the_next_configured_source_answers_when_the_first_has_nothing():
    who = resolve({"x-ms-user-identity": OTHER_OID})
    assert who.oid == OTHER_OID and who.source == "platform"


def test_the_opaque_per_user_id_is_never_an_identity():
    refused = resolve({"x-agent-user-id": "opaque-partition-key"})
    assert isinstance(refused, Refusal) and "no configured source" in refused.reason


def test_caller_supplied_headers_are_trusted_only_when_asked_for():
    signals = {"x-client-acting-user-oid": USER_OID, "x-client-acting-user-name": "Pat Writer"}
    assert isinstance(resolve(signals), Refusal)
    who = resolve(signals, sources=("client-headers",))
    assert who.oid == USER_OID and who.name == "Pat Writer" and who.source == "client-headers"


def test_a_missing_name_is_stated_not_invented():
    assert resolve({"x-ms-user-identity": USER_OID}).name == "(name not provided)"


def test_a_malformed_object_id_a_foreign_tenant_or_no_conversation_refuses():
    assert "GUID" in resolve({"x-ms-user-identity": "not-a-guid"}).reason
    assert "tenant" in resolve({"x-ms-original-subject-oid": USER_OID, "x-ms-original-subject-tid": "00000000-0000-0000-0000-0000000000ff"}).reason
    assert isinstance(resolve({"x-ms-user-identity": USER_OID}, conversation=None), Refusal)


def test_the_gateway_headers_carry_exactly_the_acting_user_and_no_credential():
    who = resolve({"x-ms-user-identity": USER_OID})
    headers = who.gateway_headers()
    assert set(headers) == {"X-Acting-User-Oid", "X-Acting-User-Name", "X-Acting-Tenant", "X-Channel", "X-Conversation-Id", "X-Correlation-Id"}
    assert headers["X-Conversation-Id"] == CONVERSATION


def test_state_is_per_person_and_conversation():
    assert resolve({"x-ms-user-identity": USER_OID}).key == (USER_OID, CONVERSATION)
    assert resolve({"x-ms-user-identity": USER_OID}, conversation="other").key != resolve({"x-ms-user-identity": USER_OID}).key


def test_the_debug_report_names_signals_and_shows_identity_values_never_a_credential():
    report = describe_signals({
        "x-ms-user-identity": USER_OID, "authorization": "Bearer secret-token", "x-agent-user-id": "opaque", "cookie": "a=b",
    })
    text = json.dumps(report)
    assert "secret-token" not in text and "authorization" not in text and "cookie" not in text
    assert report["values"] == {"x-ms-user-identity": USER_OID}
    assert "x-agent-user-id" in report["present"] and "x-agent-user-id" not in report["values"]


def test_no_identity_means_no_tool_no_model_and_a_plain_refusal():
    rig = build_rig([{"text": "never asked"}])
    reply = asyncio.run(rig.pipeline.handle("Who should we call?", None))
    assert reply.kind == "refusal" and "can't tell who you are" in reply.text
    assert rig.gateway.calls == [] and rig.chat.seen == [] and rig.gateway.narrations == []


def test_every_gateway_call_carries_the_acting_user_and_nothing_else_identifying():
    rig = build_rig([{"tools": [{"tool": "book_rank", "args": {}}]}, {"text": "The table ranks them."}])
    asyncio.run(rig.say("Who should we call first?"))
    (call,) = rig.gateway.calls
    assert call.headers["x-acting-user-oid"] == USER_OID and call.headers["x-channel"] == "teams"
    assert call.headers["x-conversation-id"] == "conv-1" and call.headers["authorization"] == "Bearer fake-token"


# ---- CH-14: x-agent-user-id as an opt-in source, and a shape report that settles whether it can be one ----


def test_the_agent_user_id_is_a_source_only_when_asked_for_and_only_when_it_is_an_object_id():
    assert isinstance(resolve({"x-agent-user-id": USER_OID}), Refusal), "off by default"
    who = resolve({"x-agent-user-id": USER_OID.upper()}, sources=("agent-user-id",))
    assert isinstance(who, ActingIdentity) and who.oid == USER_OID and who.source == "agent-user-id"
    assert who.tenant_id == TENANT.lower(), "no tenant came with it: the deployment's own is recorded"


def test_an_opaque_agent_user_id_is_no_signal_so_the_next_source_still_answers():
    who = resolve({"x-agent-user-id": "opaque-partition-key", "x-ms-user-identity": OTHER_OID}, sources=("agent-user-id", "platform"))
    assert who.oid == OTHER_OID and who.source == "platform"
    assert isinstance(resolve({"x-agent-user-id": "opaque"}, sources=("agent-user-id",)), Refusal)


def test_the_shape_report_shows_an_object_id_and_hides_an_opaque_key():
    guid = describe_signals({"x-agent-user-id": USER_OID, "x-client-acting-user-oid": USER_OID})["agent_user_id"]
    assert guid == {"kind": "guid", "length": 36, "equals_an_oid_signal": True, "value": USER_OID}
    opaque = describe_signals({"x-agent-user-id": "k" * 40})["agent_user_id"]
    assert opaque == {"kind": "opaque", "length": 40, "equals_an_oid_signal": False}
    assert describe_signals({})["agent_user_id"] is None


def test_by_default_the_platforms_agent_user_id_is_a_source_after_the_two_platform_signals():
    """Live (CH-14): for a caller's own token the platform's x-agent-user-id equalled that caller's object id."""
    rig = build_rig([], env={})
    assert rig.settings.identity_sources == ("original-subject", "platform", "agent-user-id")
