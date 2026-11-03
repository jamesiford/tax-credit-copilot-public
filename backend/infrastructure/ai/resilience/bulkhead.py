"""Bulkhead: a cap on concurrent calls to one provider. [AI-04]

A slow provider holds every request that is waiting on it. Without a cap, a model
that takes thirty seconds ties up every worker's connections until nothing else can
run. Past the limit a call is REFUSED at once rather than queued — a queue only
moves the wait — and the chain moves on to the next provider or the engine's own
answer. The refusal is outside the breaker, so shedding load never counts as the
provider being unwell.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from domain.ai import AgentSpec, ModelEvent, ModelUnavailable
from infrastructure.ai.resilience.base import RuntimeDecorator


class BulkheadFull(ModelUnavailable):
    """The provider already has its maximum concurrent calls."""

    retryable = False  # retrying immediately meets the same wall


class BulkheadRuntime(RuntimeDecorator):
    def __init__(self, inner, limit: int, telemetry: Any = None) -> None:
        super().__init__(inner)
        self._limit, self._active, self._telemetry = limit, 0, telemetry

    @property
    def active(self) -> int:
        return self._active

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        if self._active >= self._limit:
            if self._telemetry is not None:
                self._telemetry.count("ai.bulkhead_rejections", provider=self.name)
            raise BulkheadFull(f"{self.name} already has {self._limit} calls in flight")
        self._active += 1
        try:
            async for event in self._inner.stream(spec, prompt):
                yield event
        finally:
            self._active -= 1
