"""The outermost guard on a provider: egress, then (AI-04) the token budget. [AI-03]

A decorator over `AgentRuntime`, so every provider — Foundry, connection, gateway,
a test fake — passes through the same check without any of them knowing. The
decision is made PER PROVIDER because the same prompt may be allowed to Foundry
and refused to a gateway.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from application.ai.ports import AgentRuntime, EgressPolicy
from domain.ai import AgentSpec, EgressRefused, ModelEvent, ProviderStatus


class GuardedRuntime:
    def __init__(self, inner: AgentRuntime, egress: EgressPolicy) -> None:
        self._inner, self._egress = inner, egress
        self.name = inner.name

    def ready_for(self, agent_name: str) -> bool:
        return self._inner.ready_for(agent_name)

    def version_of(self, agent_name: str) -> str | None:
        return self._inner.version_of(agent_name)

    def status(self) -> ProviderStatus:
        return self._inner.status()

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        decision = self._egress.prepare(prompt, role=spec.role, provider=self.name)
        if not decision.allowed:
            raise EgressRefused(f"{self.name}: {decision.reason} (policy {decision.policy})")
        async for event in self._inner.stream(spec, decision.prompt):
            yield event
