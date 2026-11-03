"""Circuit breaker, per provider. [AI-04]

A provider that keeps failing should stop receiving traffic for a while: each doomed
call costs a timeout the reader waits through, and hammering a struggling service
delays its recovery.

    closed ──(N consecutive failures)──▶ open ──(after reset_s)──▶ half-open
       ▲                                  ▲                            │
       └────────── a probe succeeds ──────┴──── a probe fails ─────────┘

Half-open lets exactly ONE call through to find out. Only failures that say the
PROVIDER is unwell count — unavailable, timeout, rate limit, refused credentials.
A malformed request or an egress refusal is the caller's doing and must not open the
breaker. While open, `stream` fails at once; readiness is NOT affected (a breaker
decides health, not whether a pipeline is attempted — see `ai_health`), because
falling to the scripted demo stream mid-outage would show invented figures.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from domain.ai import (
    AgentSpec, ModelBadRequest, ModelEvent, ModelUnavailable, ProviderStatus,
)
from infrastructure.ai.resilience.base import RuntimeDecorator
from infrastructure.ai.resilience.clock import Clock, RealClock

CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: float, clock: Clock | None = None) -> None:
        self._threshold, self._reset, self._clock = failure_threshold, reset_seconds, clock or RealClock()
        self.state, self._failures, self._opened_at, self._probing = CLOSED, 0, 0.0, False
        self.opens = 0

    def _roll(self) -> None:
        if self.state == OPEN and self._clock.now() - self._opened_at >= self._reset:
            self.state, self._probing = HALF_OPEN, False

    def allow(self) -> bool:
        """May a call proceed? In half-open this hands out the single probe."""
        self._roll()
        if self.state == CLOSED:
            return True
        if self.state == HALF_OPEN and not self._probing:
            self._probing = True
            return True
        return False

    def success(self) -> None:
        self.state, self._failures, self._probing = CLOSED, 0, False

    def failure(self) -> None:
        self._failures += 1
        if self.state == HALF_OPEN or self._failures >= self._threshold:
            if self.state != OPEN:
                self.opens += 1
            self.state, self._opened_at, self._probing = OPEN, self._clock.now(), False

    def release_probe(self) -> None:
        self._probing = False

    @property
    def current(self) -> str:
        self._roll()
        return self.state


def counts_against_provider(error: BaseException) -> bool:
    """Does this failure say the provider is unwell?

    Everything does except a request the provider rightly refused: a bad request
    (which includes an egress refusal) is the caller's doing.
    """
    return not isinstance(error, ModelBadRequest)


class BreakerRuntime(RuntimeDecorator):
    def __init__(self, inner, breaker: CircuitBreaker, telemetry: Any = None) -> None:
        super().__init__(inner)
        self.breaker, self._telemetry = breaker, telemetry

    def status(self) -> ProviderStatus:
        state = self.breaker.current
        if state == OPEN:
            return ProviderStatus(self.name, "unavailable", "circuit open")
        if state == HALF_OPEN:
            return ProviderStatus(self.name, "degraded", "circuit half-open")
        return self._inner.status()

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        if not self.breaker.allow():
            raise ModelUnavailable(f"{self.name} is out of service (circuit open)")
        opens_before = self.breaker.opens
        try:
            async for event in self._inner.stream(spec, prompt):
                yield event
        except GeneratorExit:
            self.breaker.release_probe()
            raise
        except Exception as error:  # noqa: BLE001
            if counts_against_provider(error):
                self.breaker.failure()
                if self._telemetry is not None and self.breaker.opens > opens_before:
                    self._telemetry.count("ai.breaker_opens", provider=self.name)
            else:
                self.breaker.release_probe()
            raise
        self.breaker.success()
