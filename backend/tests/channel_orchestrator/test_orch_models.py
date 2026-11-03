"""The real model adapters, against the mock gateway, under the orchestrator's chain. [CH-08]

`OpenAICompatibleChatModel` (shared, vendored), `ModelChain` and the MAF bridge are the shipped code;
the model is `scripts/mock-ai-gateway.py` through an ASGI transport. This proves tool calls survive
the wire into MAF, a failing provider falls through to the next, a provider without tool calling is
skipped when tools are needed, and a prompt that carries an employee identifier never leaves.
"""
from __future__ import annotations

import asyncio

from app.core.models import ModelChain, Provider, foundry_openai_base
from app.core.planner import Planner
from app.core.settings import load_settings
from app.core.state import StateStore
from app.core.turn import TurnPipeline
from application.ai.safety.injection import PromptInjectionGuard
from infrastructure.ai.openai_compatible import OpenAICompatibleChatModel
from orch_harness import ENV, FakeClock, FakeGateway, identity
from tests.mock_gateway import gateway as mock_gateway
from tests.mock_gateway import settings as mock_settings


def pipeline(*providers: Provider, fake: FakeGateway | None = None, egress: str = "allow_all"):
    settings = load_settings({**ENV, "AI_EGRESS_POLICY": egress})
    fake, clock = fake or FakeGateway(), FakeClock()
    chain = ModelChain(providers, egress_policy=egress, timeout_seconds=5.0, injection=PromptInjectionGuard())
    return TurnPipeline(settings, fake.client(), Planner(chain), StateStore(3600, clock), clock), fake


def provider(name: str, *, tools: bool = True, **config):
    state, client, _ = mock_gateway(**config)
    return state, Provider(name, OpenAICompatibleChatModel(mock_settings(), client=client), f"{name}-model", tools)


def say(pipe, text: str):
    return asyncio.run(pipe.handle(text, identity()))


TREND_THEN_TEXT = (
    {"tool_calls": [{"name": "client_trend", "arguments": {}}]}, {"text": "The table shows each year."},
)


def test_a_tool_call_crosses_the_wire_into_the_maf_loop_and_back():
    state, first = provider("gateway")
    state.responses.extend(dict(r) for r in TREND_THEN_TEXT)
    pipe, fake = pipeline(first)
    reply = say(pipe, "How has Cascade trended?")
    assert reply.kind == "answer" and reply.mode == "tools" and reply.narration_used
    assert fake.tools_called() == ["client_resolve", "client_trend"]
    first_request, second_request = state.log
    assert "client_trend" in first_request["tools"] and "client_id" not in str(first_request["tools"])
    assert second_request["roles"][-1] == "tool", "the tool's result went back to the model"


def test_a_failing_provider_falls_through_to_the_next_before_any_text():
    broken_state, broken = provider("gateway")
    broken_state.faults.extend([{"kind": "status", "code": 503}])
    good_state, good = provider("foundry")
    good_state.responses.extend(dict(r) for r in TREND_THEN_TEXT)
    pipe, fake = pipeline(broken, good)
    reply = say(pipe, "How has Cascade trended?")
    assert reply.kind == "answer" and reply.narration_used
    assert len(broken_state.log) >= 1 and len(good_state.log) == 2


def test_a_provider_without_tool_calling_is_skipped_when_tools_are_needed():
    plain_state, plain = provider("gateway", tools=False)
    capable_state, capable = provider("foundry")
    capable_state.responses.extend(dict(r) for r in TREND_THEN_TEXT)
    pipe, _ = pipeline(plain, capable)
    assert say(pipe, "How has Cascade trended?").narration_used
    assert plain_state.log == []


def test_every_provider_failing_degrades_to_the_engines_own_answer():
    state, only = provider("gateway")
    state.faults.extend([{"kind": "status", "code": 503, "times": 5}])
    pipe, fake = pipeline(only)
    reply = say(pipe, "Brief me on Cascade")
    assert reply.kind == "answer" and reply.mode == "keywords" and "language model is unavailable" in reply.text
    assert fake.tools_called() == ["client_resolve", "client_situation"]


def test_a_prompt_carrying_an_employee_identifier_never_reaches_a_model():
    state, only = provider("gateway")
    pipe, fake = pipeline(only)
    reply = say(pipe, "How has Cascade trended for employee a1b2c3d4e5f6a7b8c9d0e1f2?")
    assert state.log == [], "the identifier invariant refuses every provider"
    assert reply.mode == "keywords" and "Not tax advice" in reply.text


def test_the_gateway_provider_is_external_so_aggregates_only_refuses_a_free_text_question():
    state, only = provider("gateway")
    pipe, _ = pipeline(only, egress="aggregates_only")
    reply = say(pipe, "How has Cascade trended?")
    assert state.log == [] and reply.mode == "keywords"


def test_a_foundry_project_endpoint_gives_the_accounts_openai_v1_base():
    assert foundry_openai_base("https://acct.services.ai.azure.com/api/projects/proj") == "https://acct.services.ai.azure.com/openai"
