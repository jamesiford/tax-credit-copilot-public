"""The MAF layer's structural guarantee: the Agent's only exit is the composer. [CH-08]"""
from __future__ import annotations

import asyncio

from agent_framework import Agent

from app.core.maf_agent import ComposeMiddleware, ModelTrace, PortChatClient, build_agent
from app.core.models import ModelChain, Provider
from app.core.state import ConversationState
from app.core.tools import ToolRunner
from orch_harness import FakeClock, FakeGateway, ScriptedChat, identity


def agent_for(script, composed: list[str]):
    chat = ScriptedChat(script)
    chain = ModelChain([Provider("gateway", chat, "m", True)], egress_policy="allow_all", timeout_seconds=5.0)
    gateway = FakeGateway()
    runner = ToolRunner(gateway.client(), identity(), ConversationState(), "Cascade trend", 6, 300, FakeClock())
    agent = build_agent(chain, runner, ModelTrace(), "be good", lambda raw: composed.append(raw) or f"COMPOSED<{len(raw)}>")
    return agent, runner, chat


def test_the_agent_result_is_the_composers_output_never_the_models_text():
    seen: list[str] = []
    agent, *_ = agent_for([{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "raw model words 12345"}], seen)
    result = asyncio.run(agent.run("How has Cascade trended?"))
    assert result.text == "COMPOSED<21>" and seen == ["raw model words 12345"]
    assert "12345" not in result.text


def test_an_agent_with_a_middleware_is_the_shape_that_ships():
    agent, *_ = agent_for([], [])
    assert isinstance(agent, Agent)
    assert any(isinstance(m, ComposeMiddleware) for m in agent.middleware)
    assert isinstance(agent.client, PortChatClient)


def test_the_tool_loop_is_bounded_by_the_turn_budget():
    agent, runner, chat = agent_for([{"tools": [{"tool": "client_trend", "args": {}}] * 3}] * 20 + [{"text": "done"}], [])
    runner.max_calls = 2
    asyncio.run(agent.run("How has Cascade trended?"))
    assert runner.calls <= 3, "the MAF loop stops near the budget instead of running a runaway model forever"
    assert len(chat.seen) < 20
