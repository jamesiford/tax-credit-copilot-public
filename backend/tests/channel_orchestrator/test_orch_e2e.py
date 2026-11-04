"""The orchestrator in front of the REAL gateway and the REAL API. [CH-08]

Everything else in this directory fakes the gateway. This runs the orchestrator's own `GatewayClient`
against the gateway app itself, which calls `main.app` (entra on, fake keys, SQLite stores): so what
the orchestrator sends is judged by the gateway's authentication and the API's own guard, the
confirmation protocol is proved against the real token store, and the audit rows are the ones a
person would read: the API's own begin/end pair per write step, and the gateway's `narrate` row for
the narration, all under the acting person.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "channel"))

from app.core.gateway_client import GatewayClient  # noqa: E402
from gateway_harness import OTHER_OID, USER_OID, agent_token, build_gateway  # noqa: E402
from orch_harness import build_rig, identity  # noqa: E402
from tests.test_agent_principal import entra, mint_app  # noqa: E402,F401 - fixtures
from tests.test_capabilities_equivalence import gold  # noqa: E402,F401 - fixture
from tests.test_channel_writes import world  # noqa: E402,F401 - fixture

PREPARE = {"tools": [{"tool": "engagement_set_prepare", "args": {"program_code": "GA_JTC", "scope": "in_scope", "note": "signed"}}]}
ASK = "Mark Cascade's GA_JTC engagement as in scope"


@pytest.fixture
def stack(tmp_path, entra, world):  # noqa: F811
    import main

    gw = build_gateway(tmp_path, transport=httpx.ASGITransport(app=main.app), token_provider=mint_app, writers={USER_OID})
    gw.services.pipeline._entitlement = world.writers
    gateway_audit = gw.audit
    gw.audit = world.audit
    return gw, world, gateway_audit


def orchestrator(gw, script):
    client = GatewayClient("http://gateway", agent_token, transport=httpx.ASGITransport(app=gw.client.app))
    return build_rig(script, client=client)


def say(rig, text, who="default"):
    return asyncio.run(rig.say(text, who))


def test_a_read_is_judged_by_the_real_guard_and_leaves_a_narration_row_under_the_person(stack, gold):  # noqa: F811
    gw, world_, gateway_audit = stack
    rig = orchestrator(gw, [{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "The table shows each year."}])
    reply = say(rig, "How has Cascade trended?")
    assert reply.kind == "answer" and reply.guard_status == "pass" and reply.audit == "ok", reply.text
    narrated = [e for e in gateway_audit.for_user(USER_OID) if e.action_kind == "narrate"]
    assert len(narrated) == 1
    event = narrated[0]
    assert (event.numeric_guard, event.outcome, event.is_deterministic_path, event.conversation_id) == ("pass", "ok", True, "conv-1")
    assert event.identity_assurance == "channel-asserted" and event.tool_name == "narration"
    (action,) = gw.actions.recent()
    assert action.is_deterministic_path is True and action.agent_version == "7+prompt2" and "client_trend" in action.tool_calls
    reads = [e for e in gateway_audit.for_user(USER_OID) if e.tool_name == "client_trend"]
    assert {e.user_oid for e in reads} == {USER_OID} and reads


def test_prepare_then_confirm_through_the_real_stack_writes_once_and_audits_both_steps(stack):
    gw, world_, gateway_audit = stack
    rig = orchestrator(gw, [PREPARE, {"text": "Here is the preview."}])
    preview = say(rig, ASK)
    assert preview.kind == "answer" and "Reply **confirm**" in preview.text, preview.text
    assert world_.confirmations is not None and not [e for e in world_.audit.for_user(USER_OID) if e.tool_name.endswith("_commit")]
    done = say(rig, "confirm")
    assert done.kind == "commit" and "Done" in done.text, done.text
    shape = sorted({(e.tool_name, e.phase, e.outcome) for e in world_.audit.for_user(USER_OID) if e.tool_name.startswith("engagement_set")})
    assert shape == [("engagement_set_commit", "begin", "pending"), ("engagement_set_commit", "end", "ok"),
                     ("engagement_set_prepare", "begin", "pending"), ("engagement_set_prepare", "end", "ok")]
    assert {e.identity_assurance for e in world_.audit.for_user(USER_OID)} == {"channel-asserted"}
    assert say(rig, "confirm").kind == "commit_refused", "the single use is the person's, not just the token's"


def test_somebody_elses_confirm_reaches_nothing_and_the_owners_still_works(stack):
    gw, world_, _ = stack
    rig = orchestrator(gw, [PREPARE, {"text": "Here is the preview."}])
    say(rig, ASK)
    stranger = say(rig, "confirm", identity(OTHER_OID, name="Sam Reader"))
    assert stranger.kind == "commit_refused" and not [e for e in world_.audit.for_user(OTHER_OID)]
    assert say(rig, "confirm").kind == "commit"


def test_a_person_who_may_not_write_is_refused_by_the_real_gateway_at_the_preview(stack):
    gw, world_, _ = stack
    rig = orchestrator(gw, [PREPARE, {"text": "I could not prepare that."}])
    reply = say(rig, ASK, identity(OTHER_OID, name="Sam Reader"))
    assert reply.kind == "failure" and "not entitled" in reply.text and "Reply **confirm**" not in reply.text, reply.text
    assert not [e for e in world_.audit.for_user(OTHER_OID) if e.tool_name.endswith("_commit")]
