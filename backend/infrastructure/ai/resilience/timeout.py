"""Timeout: no event for too long is a failure. [AI-04]

The limit is on the GAP between events, not on the whole call: a long, healthy
narration must not be cut off, while a connection that has gone quiet must not hold
a request open forever. The first event is where most hangs happen, so it is covered
by the same rule.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from domain.ai import AgentSpec, ModelEvent, ModelTimeout
from infrastructure.ai.resilience.base import RuntimeDecorator
from infrastructure.ai.resilience.clock import Clock, RealClock


class TimeoutRuntime(RuntimeDecorator):
    def __init__(self, inner, seconds: float, clock: Clock | None = None) -> None:
        super().__init__(inner)
        self._seconds, self._clock = seconds, clock or RealClock()

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        events = self._inner.stream(spec, prompt).__aiter__()
        try:
            while True:
                try:
                    event = await self._clock.wait_for(events.__anext__(), self._seconds)
                except StopAsyncIteration:
                    return
                except asyncio.TimeoutError as exc:
                    raise ModelTimeout(f"{self.name} produced nothing for {self._seconds:g}s") from exc
                yield event
        finally:
            await events.aclose()
