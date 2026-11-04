"""The generated MAF tools: one per offered capability, carrying nothing the catalog does not say. [RM-07]"""
from __future__ import annotations

import asyncio
import json

from agent_framework import Agent, FunctionInvocationContext

from app.core.maf_catalog_tools import TURN, catalog_tool, catalog_tools, forward_to_gateway
from app.core.models import ModelChain, Provider
from application.capabilities import catalog
from orch_harness import ScriptedChat, identity


def test_there_is_one_tool_per_tool_a_model_may_name_in_the_catalogs_own_words():
    tools = {t.name: t for t in catalog_tools()}
    assert set(tools) == {s.name for s in catalog.model_offered()}
    for spec in catalog.model_offered():
        tool = tools[spec.name]
        assert tool.description == spec.description
        assert tool.parameters() == catalog.model_schema(spec)


def test_no_generated_tool_is_a_commit_a_resolver_or_plumbing():
    names = {t.name for t in catalog_tools()}
    assert not {n for n in names if n.endswith("_commit")}
    assert not names & {"client_resolve", "employee_drill", "verify_figures", "claim_package_redeem", "channel_ping"}


def test_the_tools_are_built_once_and_carry_no_turn():
    first, second = catalog_tools(), catalog_tools()
    assert [t.name for t in first] == [t.name for t in second] == sorted(t.name for t in first)
    assert all(t.parameters()["additionalProperties"] is True for t in first)


class _Turn:
    """What a body may touch of a turn: the gateway call, as the acting person."""

    def __init__(self, who):
        self.who, self.seen = who, []

    async def forward(self, spec, args):
        self.seen.append((self.who.oid, spec.name, dict(args)))
        return {"answered_for": self.who.oid}


def _agent(tools, script):
    chain = ModelChain([Provider("gateway", ScriptedChat(script), "m", True)], egress_policy="allow_all", timeout_seconds=5.0)
    from app.core.maf_agent import PortChatClient, ModelTrace

    return Agent(PortChatClient(chain, ModelTrace(), max_calls=4), "be good", tools=tools)


def test_the_body_forwards_as_the_person_the_request_names_and_the_same_tools_serve_two_people():
    tools = catalog_tools()
    for oid in ("person-one", "person-two"):
        turn = _Turn(identity(oid))
        agent = _agent(tools, [{"tools": [{"tool": "client_trend", "args": {"client_id": 7}}]}, {"text": "done"}])
        asyncio.run(agent.run("trend", function_invocation_kwargs={TURN: turn}))
        assert turn.seen == [(oid, "client_trend", {"client_id": 7})]


def test_a_body_is_logic_free_and_returns_the_gateways_reply_untouched():
    spec = catalog.BY_NAME["client_trend"]
    turn = _Turn(identity())
    ctx = FunctionInvocationContext(function=catalog_tool(spec), arguments={}, kwargs={TURN: turn})
    reply = asyncio.run(forward_to_gateway(ctx, spec, {"client_id": 1}))
    assert reply == {"answered_for": turn.who.oid} and turn.seen[0][2] == {"client_id": 1}
    assert json.dumps(reply)
