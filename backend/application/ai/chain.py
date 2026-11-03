"""Try providers in order until one answers. [AI-02]

`ProviderChain` is itself an `AgentRuntime`, so a caller holds "a runtime" and
never knows whether that is one provider or three. The rule is the same in both
configurations the PoC demonstrates (`foundry,gateway` and `gateway,foundry`):
walk the chain, skip a provider that is not ready for this agent, move on when one
fails BEFORE producing text, and report which hop answered.

Once a provider has produced text the chain does not switch: splicing two models'
sentences would show a reader something neither said. A failure after output
began propagates, and the caller appends the engine's own blocks instead (AI-04).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

from application.ai.ports import AgentRuntime
from domain.ai import (
    AgentSpec, ModelEvent, NarrationUnavailable, ProviderStatus, StreamEnd, TextDelta,
)

log = logging.getLogger(__name__)


class ProviderChain:
    """An ordered `AgentRuntime` over other runtimes."""

    name = "chain"

    def __init__(self, runtimes: Sequence[AgentRuntime]) -> None:
        self._runtimes = tuple(runtimes)

    def ready_for(self, agent_name: str) -> bool:
        return any(rt.ready_for(agent_name) for rt in self._runtimes)

    def version_of(self, agent_name: str) -> str | None:
        return next((v for rt in self._runtimes if (v := rt.version_of(agent_name))), None)

    def status(self) -> ProviderStatus:
        states = [rt.status() for rt in self._runtimes]
        best = "ready" if any(s.state == "ready" for s in states) else (states[0].state if states else "disabled")
        return ProviderStatus("chain", best, ", ".join(f"{s.name}={s.state}" for s in states))

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        hops: list[str] = []
        for runtime in self._runtimes:
            if not runtime.ready_for(spec.name):
                continue
            hops.append(runtime.name)
            try:
                async for event in self._relay(runtime, spec, prompt, tuple(hops)):
                    yield event
                return
            except _BeforeOutput as failed:
                log.warning("provider %s failed before output (%s); trying the next", runtime.name, failed.cause)
        raise NarrationUnavailable("no provider could answer", tuple(hops))

    async def _relay(self, runtime: AgentRuntime, spec: AgentSpec, prompt: str, hops: tuple[str, ...]):
        produced, end = False, None
        try:
            async for event in runtime.stream(spec, prompt):
                if isinstance(event, StreamEnd):
                    end = event
                    continue
                produced = produced or isinstance(event, TextDelta)
                yield event
        except Exception as exc:  # noqa: BLE001 - adapters map to ModelError; a stray one still must not end the turn
            if produced:
                raise
            raise _BeforeOutput(exc) from exc
        yield StreamEnd(
            provider=runtime.name, model=getattr(end, "model", None),
            agent_version=getattr(end, "agent_version", None) or runtime.version_of(spec.name),
            hops=hops, finish_reason=getattr(end, "finish_reason", None),
        )


class _BeforeOutput(Exception):
    """A provider failed before any text: safe to try the next one."""

    def __init__(self, cause: Exception) -> None:
        super().__init__(str(cause))
        self.cause = cause
