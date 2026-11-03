"""The shared shape of every resilience decorator. [AI-04]

Each decorator wraps an `AgentRuntime` and changes how `stream` behaves; naming,
readiness and version are passed through unchanged. Written once (DRY) so a
decorator is only the behaviour it adds.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from application.ai.ports import AgentRuntime
from domain.ai import AgentSpec, ModelEvent, ProviderStatus


class RuntimeDecorator:
    """Delegates everything; subclasses override `stream` (and `status` where they know more)."""

    def __init__(self, inner: AgentRuntime) -> None:
        self._inner = inner
        self.name = inner.name

    @property
    def inner(self) -> AgentRuntime:
        return self._inner

    def ready_for(self, agent_name: str) -> bool:
        return self._inner.ready_for(agent_name)

    def version_of(self, agent_name: str) -> str | None:
        return self._inner.version_of(agent_name)

    def status(self) -> ProviderStatus:
        return self._inner.status()

    def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        return self._inner.stream(spec, prompt)
