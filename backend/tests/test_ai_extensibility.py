"""Adding a provider is one adapter and one registration, nothing else. [AI-02]

The fake below is defined INSIDE this test and registered through the public
registry API. No production file is edited to make it work — which is the claim
(open/closed), and this test is its proof: if routing a request to a new provider
ever needs a change to a pipeline, the router or a handler, this stops passing.
"""
from __future__ import annotations

import asyncio

import pytest

from application import wiring
from application.ai.providers import ProviderRegistry
from application.ai.requests import NarrateBriefQuery, RouteQuestionQuery
from application.ai.settings import AiConfigurationError, AiSettings
from domain.ai import AgentSpec, ProviderStatus, StreamEnd, TextDelta


class EchoRuntime:
    """A provider that did not exist when the application was written."""

    name = "echo"

    def ready_for(self, agent_name: str) -> bool:
        return True

    def version_of(self, agent_name: str) -> str | None:
        return "echo-1"

    def status(self) -> ProviderStatus:
        return ProviderStatus("echo", "ready")

    async def stream(self, spec: AgentSpec, prompt: str):
        yield TextDelta(f"[{spec.name}] ")
        yield TextDelta(prompt.upper())
        yield StreamEnd(provider="echo", model="echo-model")


def _collect(request):
    async def run():
        return [event async for event in wiring.get_mediator().stream(request)]

    return asyncio.run(run())


@pytest.fixture
def echo_provider():
    registry = ProviderRegistry()
    registry.register("echo", lambda settings: EchoRuntime())
    wiring.set_provider_registry(registry)
    wiring.set_ai_settings(AiSettings(provider_chain=("echo",)))
    yield registry


def test_a_registered_provider_answers_a_narration_through_the_mediator(echo_provider):
    events = _collect(NarrateBriefQuery(agent_name="ReportingAgent", prompt="annual credit"))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "[ReportingAgent] ANNUAL CREDIT"
    end = events[-1]
    assert isinstance(end, StreamEnd) and end.provider == "echo" and end.hops == ("echo",)
    assert end.agent_version == "echo-1"


def test_the_same_provider_serves_routing_on_the_router_role(echo_provider):
    events = _collect(RouteQuestionQuery(prompt="who should we call"))
    assert "".join(e.text for e in events if isinstance(e, TextDelta)).startswith("[OrchestratorAgent]")


def test_the_new_provider_makes_the_chat_available(echo_provider):
    from application.ai.specs import CHAT_PIPELINE_AGENTS

    assert wiring.get_narration_service().available(CHAT_PIPELINE_AGENTS)


def test_a_provider_can_serve_one_role_only(echo_provider):
    from domain.ai import ModelRole

    registry = wiring.get_provider_registry()
    registry.register("quiet", lambda settings: type("Q", (EchoRuntime,), {"name": "quiet"})())
    wiring.set_ai_settings(AiSettings(
        provider_chain=("quiet",), role_chains={ModelRole.NARRATOR: ("echo",)},
    ))
    narrated = _collect(NarrateBriefQuery(agent_name="ReportingAgent", prompt="x"))
    routed = _collect(RouteQuestionQuery(prompt="y"))
    assert narrated[-1].provider == "echo" and routed[-1].provider == "quiet"


def test_an_unregistered_provider_name_is_a_clear_configuration_error():
    wiring.set_ai_settings(AiSettings(provider_chain=("nonesuch",)))
    with pytest.raises(AiConfigurationError, match="unknown provider 'nonesuch'"):
        _collect(NarrateBriefQuery(agent_name="ReportingAgent", prompt="x"))


def test_registering_a_name_twice_is_refused():
    registry = ProviderRegistry()
    registry.register("echo", lambda s: EchoRuntime())
    with pytest.raises(ValueError, match="already registered"):
        registry.register("echo", lambda s: EchoRuntime())


def test_streaming_and_sending_are_not_interchangeable():
    mediator = wiring.get_mediator()
    with pytest.raises(TypeError, match="stream"):
        mediator.send(NarrateBriefQuery(agent_name="ReportingAgent", prompt="x"))

    async def misuse():
        from application.queries.get_proximity import GetProximityQuery

        async for _ in mediator.stream(GetProximityQuery(tax_year=2023, state="GA")):
            pass

    with pytest.raises(TypeError, match="not a StreamingQuery"):
        asyncio.run(misuse())


def test_a_narration_request_must_name_an_agent_and_a_prompt():
    with pytest.raises(ValueError):
        _collect(NarrateBriefQuery(agent_name="", prompt="x"))
