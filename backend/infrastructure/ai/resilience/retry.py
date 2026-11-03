"""Retry with exponential backoff and full jitter. [AI-04]

One implementation of retrying (DRY) for every provider. The rules:

- Retry only what can succeed later: a `ModelError` whose `retryable` is true
  (unavailable, timeout, rate limited). A 4xx other than 429, a refused credential
  and an egress refusal are never retried — repeating them only adds load.
- Retry only BEFORE output. Once text has reached the reader a second attempt would
  repeat or contradict it; the failure propagates instead.
- Honour `Retry-After` when the provider said how long to wait; otherwise wait a
  random time up to `base * 2^(attempt-1)`, capped at `max` ("full jitter", so a
  fleet of callers does not retry in lockstep).
- Bounded twice: by attempts and by a total deadline across attempts, so a retry
  loop can never outlive the request that started it.
"""
from __future__ import annotations

import random
from collections.abc import AsyncIterator
from typing import Any

from application.ai.settings import ResilienceSettings
from domain.ai import AgentSpec, ModelError, ModelEvent, ModelRateLimited, TextDelta
from infrastructure.ai.resilience.base import RuntimeDecorator
from infrastructure.ai.resilience.clock import Clock, RealClock


class RetryRuntime(RuntimeDecorator):
    def __init__(
        self, inner, policy: ResilienceSettings, clock: Clock | None = None,
        rng: random.Random | None = None, telemetry: Any = None,
    ) -> None:
        super().__init__(inner)
        self._p, self._clock = policy, clock or RealClock()
        self._rng, self._telemetry = rng or random.Random(), telemetry

    def delay_for(self, attempt: int, error: ModelError) -> float:
        """How long to wait before attempt `attempt + 1`."""
        if isinstance(error, ModelRateLimited) and error.retry_after is not None:
            return error.retry_after
        return self._rng.uniform(0, min(self._p.retry_max_s, self._p.retry_base_s * 2 ** (attempt - 1)))

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        started, attempt = self._clock.now(), 0
        while True:
            attempt += 1
            produced = False
            try:
                async for event in self._inner.stream(spec, prompt):
                    produced = produced or isinstance(event, TextDelta)
                    yield event
                return
            except ModelError as error:
                if produced or not error.retryable or attempt >= self._p.retry_attempts:
                    raise
                delay = self.delay_for(attempt, error)
                if self._clock.now() - started + delay > self._p.total_deadline_s:
                    raise
                if self._telemetry is not None:
                    self._telemetry.count("ai.retries", provider=self.name)
                await self._clock.sleep(delay)
