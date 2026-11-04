"""Gateway narration end to end, in both chain orders. [AI-03]

`foundry,gateway` and `gateway,foundry` are both configuration. This runs the real
composition (settings -> registry -> router -> guarded chain -> mediator) against
the mock gateway, with a scripted Foundry beside it, and checks the three things
the PoC will demonstrate: the preferred provider answers, a dead one falls
through, and the hop that answered is recorded.
"""
from __future__ import annotations

import asyncio

import pytest

from bootstrap import wiring
from application.ai.providers import ProviderRegistry
from application.ai.requests import NarrateBriefQuery, RouteQuestionQuery
from application.ai.settings import load_ai_settings
from domain.ai import ModelUnavailable, StreamEnd, TextDelta
from infrastructure.ai.chat_model_runtime import ChatModelAgentRuntime
from infrastructure.ai.openai_compatible import OpenAICompatibleChatModel
from tests.ai_fakes import ScriptedRuntime
from tests.mock_gateway import gateway, settings

ENV = {"AI_GATEWAY_ENDPOINT": "https://mock.invalid", "AI_GATEWAY_AUTH": "none",
       "AI_MODEL_NARRATOR__GATEWAY": "mock-model", "AI_MODEL_ROUTER__GATEWAY": "mock-model"}


def compose(chain: str, foundry: ScriptedRuntime, **extra_env):
    """The real settings and router, with the network pieces swapped for doubles."""
    state, client, _ = gateway()
    wiring.reset_ai()
    s = load_ai_settings({**ENV, "AI_PROVIDER_CHAIN": chain, **extra_env})
    registry = ProviderRegistry()
    registry.register("foundry", lambda _s: foundry)
    registry.register("gateway", lambda cfg: ChatModelAgentRuntime(
        OpenAICompatibleChatModel(settings(), client=client), cfg))
    wiring.set_ai_settings(s)
    wiring.set_provider_registry(registry)
    return state


def narrate(prompt="Summarise the credit."):
    async def go():
        return [e async for e in wiring.get_mediator().stream(NarrateBriefQuery(agent_name="ReportingAgent", prompt=prompt))]

    return asyncio.run(go())


def text(events):
    return "".join(e.text for e in events if isinstance(e, TextDelta))


@pytest.mark.parametrize("chain, first", [("foundry,gateway", "foundry"), ("gateway,foundry", "gateway")])
def test_the_first_provider_in_the_chain_answers(chain, first):
    foundry = ScriptedRuntime("foundry", ["from foundry"])
    state = compose(chain, foundry)
    state.responses.append({"text": "from gateway"})
    events = narrate()
    assert text(events) == f"from {first}" and events[-1].provider == first and events[-1].hops == (first,)


def test_foundry_down_falls_through_to_the_gateway_and_the_hops_say_so():
    state = compose("foundry,gateway", ScriptedRuntime("foundry", error=ModelUnavailable("project unreachable")))
    state.responses.append({"text": "the gateway answered"})
    events = narrate()
    assert text(events) == "the gateway answered"
    end = events[-1]
    assert isinstance(end, StreamEnd) and end.hops == ("foundry", "gateway") and end.fallback_used


def test_a_single_gateway_blip_is_retried_and_the_chain_never_leaves_the_gateway():
    state = compose("gateway,foundry", foundry := ScriptedRuntime("foundry", ["foundry covered"]))
    state.faults.append({"kind": "status", "code": 503})
    state.responses.append({"text": "from gateway"})
    events = narrate()
    assert text(events) == "from gateway" and events[-1].hops == ("gateway",)
    assert foundry.calls == 0


def test_a_retry_after_header_is_waited_out_on_the_clock_not_the_wall():
    from infrastructure.ai.resilience.clock import FakeClock

    state = compose("gateway,foundry", ScriptedRuntime("foundry", ["covered"]))
    clock = FakeClock()
    wiring.set_ai_clock(clock)
    state.faults.append({"kind": "status", "code": 429, "retry_after": 2})
    state.responses.append({"text": "from gateway"})
    assert text(narrate()) == "from gateway" and clock.sleeps == [2.0]


def test_a_gateway_that_keeps_failing_opens_its_breaker_and_stops_being_called():
    foundry = ScriptedRuntime("foundry", ["covered"])
    state = compose("gateway,foundry", foundry, AI_BREAKER_FAILURE_THRESHOLD="2", AI_RETRY_MAX_ATTEMPTS="1")
    state.faults.extend([{"kind": "status", "code": 503}] * 50)
    for _ in range(4):
        assert text(narrate()) == "covered"
    assert len(state.faults) == 48, "two calls reached the gateway; the open breaker kept the other two away"


def test_the_gateway_down_falls_through_to_foundry():
    state = compose("gateway,foundry", ScriptedRuntime("foundry", ["foundry covered"]))
    state.faults.extend([{"kind": "status", "code": 503}] * 3)  # every retry attempt
    events = narrate()
    assert text(events) == "foundry covered" and events[-1].hops == ("gateway", "foundry")


def test_a_rate_limited_gateway_falls_through_too():
    state = compose("gateway,foundry", ScriptedRuntime("foundry", ["covered"]))
    state.faults.extend([{"kind": "status", "code": 429, "retry_after": 2}] * 3)
    assert text(narrate()) == "covered"


def test_a_per_role_chain_puts_the_narrator_on_the_gateway_and_the_router_on_foundry():
    foundry = ScriptedRuntime("foundry", ["routed"])
    state = compose("foundry", foundry, AI_PROVIDER_CHAIN__NARRATOR="gateway")
    state.responses.append({"text": "narrated"})

    async def route():
        return [e async for e in wiring.get_mediator().stream(RouteQuestionQuery(prompt="who"))]

    assert text(narrate()) == "narrated" and text(asyncio.run(route())) == "routed"


def test_the_gateway_receives_the_agents_instructions_as_the_system_message_and_the_role_model():
    state = compose("gateway", ScriptedRuntime("foundry"))
    narrate("the brief")
    entry = state.log[0]
    assert entry["roles"] == ["system", "user"] and entry["model"] == "mock-model" and entry["tools"] == []


def test_the_chat_stub_is_used_when_no_provider_is_ready():
    from application.ai.specs import CHAT_PIPELINE_AGENTS

    compose("foundry,gateway", ScriptedRuntime("foundry", ready=False))
    # the gateway is always ready (specs are in-process), so the chat is available through it
    assert wiring.get_narration_service().available(CHAT_PIPELINE_AGENTS)
    compose("foundry", ScriptedRuntime("foundry", ready=False))
    assert not wiring.get_narration_service().available(CHAT_PIPELINE_AGENTS)


def test_the_real_gateway_factory_builds_from_settings_without_touching_the_network():
    wiring.reset_ai()
    s = load_ai_settings({**ENV, "AI_PROVIDER_CHAIN": "gateway"})
    wiring.set_ai_settings(s)
    runtime = wiring.get_provider_registry().build("gateway", s)
    assert isinstance(runtime, ChatModelAgentRuntime) and runtime.ready_for("ReportingAgent")
    assert runtime.status().state == "ready"
