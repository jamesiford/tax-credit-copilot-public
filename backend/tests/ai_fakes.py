"""Test doubles for model access. [AI-02]

A real `FoundryAgentRuntime` over a stub catalog and a fake agent, so tests run
the production mapping and streaming code rather than a re-implementation of it;
and a scripted `AgentRuntime` for provider-chain tests.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from application import wiring
from application.ai.providers import ProviderRegistry
from application.ai.settings import AiSettings
from domain.ai import AgentSpec, ModelEvent, ProviderStatus, StreamEnd, TextDelta
from infrastructure.ai.foundry_prompt_agents import FoundryAgentRuntime
from infrastructure.ai.foundry_publish import PublishedAgent


class FakeAgent:
    """Stands in for `agent_framework_foundry.FoundryAgent`: `run(prompt, stream=True)`."""

    agent_version = "7"

    def __init__(self, chunks: Sequence[str] = ("Hello ", "world"), fail: bool = False, error: Exception | None = None):
        self.chunks, self.fail, self.error = chunks, fail, error
        self.prompts: list[str] = []

    async def run(self, prompt, stream=True):
        self.prompts.append(prompt)
        if self.error is not None and not self.chunks:
            raise self.error
        for chunk in self.chunks:
            yield type("U", (), {"text": chunk})()
        if self.fail:
            raise RuntimeError("model down")


class StubCatalog:
    """Every agent is published; nothing talks to Foundry."""

    provider = "foundry"
    endpoint = "https://example.invalid/api/projects/p"

    def has(self, agent_name: str) -> bool:
        return True

    def entry(self, agent_name: str) -> PublishedAgent:
        return PublishedAgent(agent_name, "3", "id", "url", "gpt-test", agent_name)

    def version_of(self, agent_name: str) -> str:
        return "3"

    def status(self) -> ProviderStatus:
        return ProviderStatus("foundry", "ready")


def foundry_runtime_over(agent: FakeAgent) -> FoundryAgentRuntime:
    return FoundryAgentRuntime(StubCatalog(), agent_factory=lambda entry: agent)


class ScriptedRuntime:
    """An `AgentRuntime` that plays a script: text chunks, then optionally an error."""

    def __init__(self, name: str, chunks: Sequence[str] = ("ok",), error: Exception | None = None,
                 error_after_output: bool = False, ready: bool = True):
        self.name, self.chunks, self.error = name, tuple(chunks), error
        self.error_after_output, self.ready, self.calls = error_after_output, ready, 0

    def ready_for(self, agent_name: str) -> bool:
        return self.ready

    def version_of(self, agent_name: str) -> str | None:
        return "v-" + self.name

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, "ready" if self.ready else "unavailable")

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        self.calls += 1
        if self.error is not None and not self.error_after_output:
            raise self.error
        for chunk in self.chunks:
            yield TextDelta(chunk)
        if self.error is not None:
            raise self.error
        yield StreamEnd(provider=self.name, model="m-" + self.name)


class FlakyRuntime(ScriptedRuntime):
    """Plays one outcome per call: an exception to raise, or text to answer with.

    `after` lets an outcome produce some text first and then fail, which is what a
    connection dropped mid-sentence looks like.
    """

    def __init__(self, name: str, outcomes: Sequence[Exception | str], *, after: str = ""):
        super().__init__(name)
        self.outcomes, self.after = list(outcomes), after

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        self.calls += 1
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            if self.after:
                yield TextDelta(self.after)
            raise outcome
        yield TextDelta(outcome)
        yield StreamEnd(provider=self.name, model="m-" + self.name)


class HangingRuntime(ScriptedRuntime):
    """Takes `delays` seconds (on the given clock) before each event."""

    def __init__(self, name: str, clock, delays: Sequence[float]):
        super().__init__(name)
        self.clock, self.delays = clock, tuple(delays)

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        self.calls += 1
        for delay in self.delays:
            await self.clock.sleep(delay)
            yield TextDelta("x")
        yield StreamEnd(provider=self.name)


def install_providers(*runtimes, chain: Sequence[str] | None = None, **settings) -> None:
    """Make `runtimes` the app's providers, in `chain` order (default: the order given)."""
    wiring.reset_ai()
    registry = ProviderRegistry()
    for runtime in runtimes:
        registry.register(runtime.name, lambda _s, runtime=runtime: runtime)
    wiring.set_provider_registry(registry)
    wiring.set_ai_settings(AiSettings(provider_chain=tuple(chain or [r.name for r in runtimes]), **settings))
