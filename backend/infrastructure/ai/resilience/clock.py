"""Time, as a thing a test can control. [AI-04]

Retry backoff, breaker reset and call timeouts are all about time, and a test that
sleeps for real is slow and flaky. Every resilience class takes a `Clock`; production
uses the real one and tests use `FakeClock`, whose `sleep` advances virtual time and
returns at once — so "retry waits 0.5 s, then 1 s, then gives up at the 45 s
deadline" is asserted exactly, in microseconds.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from typing import Protocol, TypeVar

T = TypeVar("T")


class Clock(Protocol):
    """Time as a dependency: `now`, `sleep` and a bounded wait, all replaceable in a test."""

    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    async def wait_for(self, awaitable: Awaitable[T], seconds: float) -> T: ...


class RealClock:
    """Monotonic time, real sleeping, real cancellation on timeout."""

    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def wait_for(self, awaitable: Awaitable[T], seconds: float) -> T:
        return await asyncio.wait_for(awaitable, seconds)


class InstantClock(RealClock):
    """Real time and real timeouts, but `sleep` returns at once.

    For the suite at large: code that retries must not make a test wait out a real
    backoff. Time that was "slept" is added to `now()` so deadlines still see it.
    """

    def __init__(self) -> None:
        self._slept = 0.0

    def now(self) -> float:
        return time.monotonic() + self._slept

    async def sleep(self, seconds: float) -> None:
        self._slept += max(seconds, 0.0)
        await asyncio.sleep(0)


class FakeClock:
    """Virtual time. `sleep` advances it instantly; `wait_for` times out if the awaited
    work advanced virtual time past `seconds` (a hang is `await clock.sleep(1e6)`)."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._now += max(seconds, 0.0)

    def advance(self, seconds: float) -> None:
        self._now += seconds

    async def wait_for(self, awaitable: Awaitable[T], seconds: float) -> T:
        started = self._now
        result = await awaitable
        if self._now - started > seconds:
            raise asyncio.TimeoutError
        return result
