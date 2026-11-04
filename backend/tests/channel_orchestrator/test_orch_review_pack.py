"""RM-10c: the client review pack is a MAF Workflow, run through the same rules and the same composer as every answer. [CH-08, RM-10c]

A fixed sequence (resolve the client, read the position, check, compose) with no model in it. The figures are the
gateway's own; the reply is the platform's blocks through the verbatim composer and the numeric guard; each step is
a call to one catalog capability through the turn's rules, so the arguments the gateway sees are the ones an
Agent's call would have produced for the same words.
"""
from __future__ import annotations

import asyncio
import re

import pytest

from app.core.compose import allowed_for, facts_of
from app.core.maf_review_pack import PackRequest, build_pack_flow
from app.core.planned import Planned
from app.core.review_pack import CALL_LIMIT, MODE, step_tools, wants_review_pack
from app.core.state import ConversationState
from app.core.tools import ToolRunner
from application.capabilities import catalog
from application.numeric.guard import FactIndex, check
from orch_harness import FakeClock, FakeGateway, build_rig, identity

ASK = "Give me a client review pack for Cascade for 2023"
POSITION_CALLS = ["client_resolve", "client_situation", "client_eligibility", "client_eligibility", "client_trend", "client_at_risk", "client_discovery"]


def say(rig, text, who="default"):
    return asyncio.run(rig.say(text, identity() if who == "default" else who))


# --------------------------------------------------------------------- the request


@pytest.mark.parametrize("text", [
    "Give me a client review pack for Cascade", "review pack for Northwind", "Prepare the credit review for Ironbridge",
    "Can I have a client briefing on Cascade?", "client review: Cascade 2023", "CLIENT REVIEW PACK",
])
def test_the_pack_is_asked_for_by_name(text):
    assert wants_review_pack(text)


@pytest.mark.parametrize("text", [
    "Brief me on Cascade", "Give me a brief on Northwind Care Systems before my call", "Tell me everything about Cascade for 2023",
    "Walk me through Cascade's credit", "What is Cascade's credit for 2023?", "Who should we call first?", "How has Cascade trended?", "",
])
def test_an_ordinary_question_is_not_the_pack(text):
    assert not wants_review_pack(text)


def test_the_steps_are_catalog_tools_that_only_read_and_the_sequence_has_its_own_budget():
    tools = step_tools()
    assert tools == [catalog.CHAT_INTENT_TOOL[i] for i in ("situation", "eligibility", "trend", "at_risk", "discovery")]
    offered = {s.name: s for s in catalog.model_offered()}
    assert all(t in offered and offered[t].kind == catalog.READ for t in tools), "the pack reads: it never prepares or commits"
    assert CALL_LIMIT == len(tools) + 1, "every step once, and eligibility's second certified method"


# ------------------------------------------------------------------ the sequence


def test_the_pack_runs_every_step_in_order_through_the_gateway_with_no_model():
    rig = build_rig([{"text": "a model must not be asked"}])
    reply = say(rig, ASK)
    assert reply.kind == "answer" and reply.mode == MODE and not reply.narration_used and reply.audit == "skipped"
    assert rig.gateway.tools_called() == POSITION_CALLS and rig.chat.seen == [], "no model took part"
    assert [run.label for run in reply.runs] == [
        "client_situation", "client_eligibility_min_max", "client_eligibility_pay_period", "client_trend", "client_at_risk", "client_discovery",
    ]
    for figure in ("375.53", "494.25", "$227,605", "$643,125", "410.13"):
        assert figure in reply.text, f"{figure} is the engine's, shown as it was returned"
    assert "Not tax advice" in reply.text and "_Source: run run-0001" in reply.text and "read-only position" in reply.text


def test_the_reply_passes_the_numeric_guard_against_the_runs_own_facts():
    reply = say(build_rig([]), ASK)
    body = re.sub(r"\*\*|\|", " ", "\n".join(l for l in reply.text.splitlines() if not l.startswith("_")))
    verdict = check(body, facts=FactIndex.coerce(facts_of(reply.runs)), allowed_context=allowed_for(ASK, reply.runs))
    assert verdict.passed, [v.numeral.text for v in verdict.violations]
    assert reply.guard_status == "pass"


def test_each_step_sends_the_gateway_what_an_agents_call_for_the_same_words_would():
    pack = build_rig([])
    say(pack, ASK)
    agent = build_rig([{"tools": [{"tool": "client_eligibility", "args": {}}, {"tool": "client_trend", "args": {}}]}, {"text": "ok"}])
    say(agent, ASK.replace("a client review pack", "the position"))
    for tool in ("client_eligibility", "client_trend"):
        assert [c.args for c in pack.gateway.calls if c.tool == tool] == [c.args for c in agent.gateway.calls if c.tool == tool]


def test_a_configured_tool_calling_model_is_not_asked_for_the_pack():
    rig = build_rig([{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "never used"}])
    reply = say(rig, ASK)
    assert reply.mode == MODE and rig.chat.seen == [] and len(rig.chat.script) == 2


def test_the_sequence_has_its_own_budget_whatever_the_agents_is():
    rig = build_rig([], env={"CHANNEL_MAX_TOOL_CALLS": "1"})
    reply = say(rig, ASK)
    assert reply.kind == "answer" and rig.gateway.tools_called() == POSITION_CALLS and not reply.refused


def test_the_pack_changes_nothing_and_asks_for_no_confirmation():
    rig = build_rig([])
    reply = say(rig, ASK)
    assert not [t for t in rig.gateway.tools_called() if t.endswith(("_prepare", "_commit"))]
    assert "Reply **confirm**" not in reply.text and rig.pipeline._store.get(identity().key).write is None


# ------------------------------------------------------------- asking back


def test_a_missing_year_is_asked_for_and_the_next_message_may_be_only_the_year():
    rig = build_rig([])
    first = say(rig, "Give me a client review pack for Cascade")
    assert first.kind == "clarify" and "Which tax year do you mean?" in first.text
    assert "client_trend" not in rig.gateway.tools_called()
    before = len(rig.gateway.calls)
    second = say(rig, "2023")
    assert second.kind == "answer" and second.mode == MODE
    assert {c.args.get("tax_year") for c in rig.gateway.calls[before:] if c.tool == "client_eligibility"} == {2023}


def test_an_ambiguous_client_is_asked_for_and_the_numbered_reply_runs_the_pack_for_the_one_chosen():
    rig = build_rig([])
    first = say(rig, "Client review pack for Cascade and Northwind for 2023")
    assert first.kind == "clarify" and "1) Cascade Retail Partners" in first.text
    second = say(rig, "2")
    assert second.kind == "answer" and second.mode == MODE
    assert {c.args.get("client_id") for c in rig.gateway.calls if c.tool == "client_trend"} == {2002}


def test_a_year_is_not_taken_from_a_message_that_is_not_answering_a_pack():
    rig = build_rig([])
    say(rig, "What is Cascade's credit?")
    reply = say(rig, "2023")
    assert reply.mode != MODE


# ------------------------------------------------------------------ failures


def test_a_step_that_fails_is_reported_and_the_others_still_answer():
    gateway = FakeGateway()
    gateway.overrides["client_trend"] = lambda _a: (502, {"error": {"code": "api_unreachable", "message": "down", "retryable": True}})
    reply = say(build_rig([], gateway=gateway), ASK)
    assert reply.kind == "answer" and "375.53" in reply.text and "410.13" not in reply.text
    assert "calculation service did not answer" in reply.text and "client_trend" not in [r.name for r in reply.runs]


def test_when_nothing_answers_the_check_stops_the_pack_and_the_reader_is_told_so_without_a_figure():
    gateway = FakeGateway()
    for tool in step_tools():
        gateway.overrides[tool] = lambda _a: (502, {"error": {"code": "api_unreachable", "message": "down", "retryable": True}})
    reply = say(build_rig([], gateway=gateway), ASK)
    assert reply.kind == "failure" and "calculation service did not answer" in reply.text and reply.runs == ()


# ------------------------------------------------------------------- the shape


def test_the_workflow_is_one_chain_from_resolve_to_compose_with_a_step_per_catalog_tool():
    runner = ToolRunner(FakeGateway().client(), identity(), ConversationState(), ASK, CALL_LIMIT, 300, FakeClock())
    flow = build_pack_flow(runner, Planned(MODE))
    assert flow.input_types == [PackRequest]
    assert list(flow.executors) == ["resolve_client", *[f"step_{t}" for t in step_tools()], "check", "compose"]
    edges = [(e.source_id, e.target_id) for g in flow.edge_groups for e in g.edges if not e.source_id.startswith("internal:")]
    order = list(flow.executors)
    assert edges == list(zip(order, order[1:])), "a chain: no branch a model could take"
