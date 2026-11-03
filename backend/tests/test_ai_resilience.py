"""The resilience decorators, one behaviour at a time, on virtual time. [AI-04]

No test here sleeps: `FakeClock.sleep` advances a counter, so "waits 0.5 s then 1 s,
then gives up at the deadline" is asserted exactly and runs in microseconds.
"""
from __future__ import annotations

import asyncio
import random

import pytest

from application.ai.settings import ResilienceSettings
from domain.ai import (
    AgentSpec, ModelAuth, ModelBadRequest, ModelRateLimited, ModelTimeout, ModelUnavailable, TextDelta,
)
from infrastructure.ai.resilience import (
    BreakerRuntime, BulkheadRuntime, RetryRuntime, TimeoutRuntime, build_resilient_runtime,
)
from infrastructure.ai.resilience.breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker
from infrastructure.ai.resilience.bulkhead import BulkheadFull
from infrastructure.ai.resilience.clock import FakeClock
from tests.ai_fakes import FlakyRuntime, HangingRuntime

SPEC = AgentSpec(name="ReportingAgent", instructions="x")
POLICY = ResilienceSettings(
    call_timeout_s=5, retry_attempts=3, retry_base_s=0.5, retry_max_s=8, total_deadline_s=45,
    breaker_failures=3, breaker_reset_s=30, bulkhead_limit=2,
)


class TopOfRange(random.Random):
    """Always picks the top of the jitter range, so the backoff is exactly base * 2^n."""

    def uniform(self, a, b):
        return b


def collect(runtime, prompt="p"):
    async def go():
        return [e async for e in runtime.stream(SPEC, prompt)]

    return asyncio.run(go())


def text(events):
    return "".join(e.text for e in events if isinstance(e, TextDelta))


def retrying(inner, clock, policy=POLICY):
    return RetryRuntime(inner, policy, clock, TopOfRange())


# --- retry -----------------------------------------------------------------------

def test_a_transient_failure_is_retried_with_exponential_backoff():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("x"), ModelTimeout("y"), "answer"])
    assert text(collect(retrying(inner, clock))) == "answer"
    assert inner.calls == 3 and clock.sleeps == [0.5, 1.0]


def test_jitter_stays_within_the_backoff_ceiling():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("x")] * 3)
    runtime = RetryRuntime(inner, POLICY, clock, random.Random(7))
    with pytest.raises(ModelUnavailable):
        collect(runtime)
    assert all(0 <= s <= cap for s, cap in zip(clock.sleeps, [0.5, 1.0]))


def test_retry_after_from_the_provider_is_honoured():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelRateLimited("slow down", retry_after=3.0), "ok"])
    collect(retrying(inner, clock))
    assert clock.sleeps == [3.0]


@pytest.mark.parametrize("error", [ModelBadRequest("no"), ModelAuth("denied")])
def test_a_client_error_is_never_retried(error):
    clock, inner = FakeClock(), FlakyRuntime("p", [error])
    with pytest.raises(type(error)):
        collect(retrying(inner, clock))
    assert inner.calls == 1 and clock.sleeps == []


def test_nothing_is_retried_once_text_has_been_sent():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("dropped")], after="partial ")
    events = []

    async def go():
        async for event in retrying(inner, clock).stream(SPEC, "p"):
            events.append(event)

    with pytest.raises(ModelUnavailable):
        asyncio.run(go())
    assert text(events) == "partial " and inner.calls == 1


def test_attempts_are_bounded():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("down")])
    with pytest.raises(ModelUnavailable):
        collect(retrying(inner, clock))
    assert inner.calls == POLICY.retry_attempts


def test_the_total_deadline_stops_retrying_before_the_attempts_run_out():
    tight = ResilienceSettings(retry_attempts=10, retry_base_s=0.5, retry_max_s=8, total_deadline_s=1.0)
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("down")])
    with pytest.raises(ModelUnavailable):
        collect(retrying(inner, clock, tight))
    # 0.5 s fits inside 1 s; the next wait (1.0 s) would cross it, so it is not taken.
    assert inner.calls == 2 and clock.sleeps == [0.5]


# --- timeout ---------------------------------------------------------------------

def test_a_silent_provider_times_out():
    clock = FakeClock()
    with pytest.raises(ModelTimeout):
        collect(TimeoutRuntime(HangingRuntime("p", clock, [100]), 5, clock))


def test_the_timeout_is_a_gap_between_events_not_a_cap_on_the_whole_call():
    clock = FakeClock()
    slow_but_alive = HangingRuntime("p", clock, [4, 4, 4, 4])  # 16 s in all, never 5 s quiet
    assert text(collect(TimeoutRuntime(slow_but_alive, 5, clock))) == "xxxx"


def test_a_quiet_gap_after_the_first_event_also_times_out():
    clock = FakeClock()
    with pytest.raises(ModelTimeout):
        collect(TimeoutRuntime(HangingRuntime("p", clock, [1, 60]), 5, clock))


# --- breaker ---------------------------------------------------------------------

def breaker_over(inner, clock, failures=3):
    return BreakerRuntime(inner, CircuitBreaker(failures, 30, clock))


def fail_n(runtime, n):
    for _ in range(n):
        with pytest.raises(Exception):
            collect(runtime)


def test_the_breaker_opens_after_consecutive_failures_and_then_refuses_fast():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("down")])
    runtime = breaker_over(inner, clock)
    fail_n(runtime, 3)
    assert runtime.breaker.state == OPEN and runtime.status().state == "unavailable"
    with pytest.raises(ModelUnavailable, match="circuit open"):
        collect(runtime)
    assert inner.calls == 3, "an open breaker must not reach the provider"


def test_a_success_resets_the_failure_count():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("x"), ModelUnavailable("x"), "ok", ModelUnavailable("x")])
    runtime = breaker_over(inner, clock)
    fail_n(runtime, 2)
    collect(runtime)
    fail_n(runtime, 1)
    assert runtime.breaker.state == CLOSED


def test_after_the_reset_period_one_probe_closes_the_breaker_on_success():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("x")] * 3 + ["back"])
    runtime = breaker_over(inner, clock)
    fail_n(runtime, 3)
    clock.advance(30)
    assert runtime.breaker.current == HALF_OPEN and runtime.status().state == "degraded"
    assert text(collect(runtime)) == "back" and runtime.breaker.state == CLOSED


def test_a_failed_probe_reopens_the_breaker():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("x")])
    runtime = breaker_over(inner, clock)
    fail_n(runtime, 3)
    clock.advance(30)
    fail_n(runtime, 1)
    assert runtime.breaker.state == OPEN and inner.calls == 4


def test_half_open_lets_exactly_one_probe_through():
    breaker = CircuitBreaker(1, 10, clock := FakeClock())
    breaker.failure()
    clock.advance(10)
    assert breaker.allow() is True and breaker.allow() is False


def test_a_rejected_request_does_not_count_against_the_provider():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelBadRequest("malformed")])
    runtime = breaker_over(inner, clock)
    fail_n(runtime, 10)
    assert runtime.breaker.state == CLOSED


# --- bulkhead --------------------------------------------------------------------

def test_a_call_over_the_concurrency_limit_is_refused_at_once():
    async def go():
        runtime = BulkheadRuntime(HangingRuntime("p", FakeClock(), [1, 1]), limit=1)
        first = runtime.stream(SPEC, "p")
        await first.__anext__()
        assert runtime.active == 1
        with pytest.raises(BulkheadFull):
            await runtime.stream(SPEC, "p").__anext__()
        await first.aclose()
        assert runtime.active == 0
        return [e async for e in runtime.stream(SPEC, "p")]

    assert text(asyncio.run(go())) == "xx"


def test_shedding_load_is_not_a_provider_failure():
    assert BulkheadFull("x").retryable is False


# --- the stack -------------------------------------------------------------------

def test_the_stack_is_bulkhead_breaker_retry_timeout_in_that_order():
    stack = build_resilient_runtime(FlakyRuntime("p", ["ok"]), POLICY, clock=FakeClock())
    layers = []
    while hasattr(stack, "inner"):
        layers.append(type(stack).__name__)
        stack = stack.inner
    assert layers == ["BulkheadRuntime", "BreakerRuntime", "RetryRuntime", "TimeoutRuntime"]


def test_one_request_that_retries_is_one_breaker_failure_not_three():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("down")])
    stack = build_resilient_runtime(inner, POLICY, clock=clock, rng=TopOfRange())
    fail_n(stack, 1)
    assert inner.calls == POLICY.retry_attempts
    assert stack.inner.breaker.state == CLOSED, "three attempts of one request must not trip a threshold of three"


def test_a_provider_that_recovers_mid_retry_never_surfaces_the_failure():
    clock, inner = FakeClock(), FlakyRuntime("p", [ModelUnavailable("blip"), "fine"])
    assert text(collect(build_resilient_runtime(inner, POLICY, clock=clock, rng=TopOfRange()))) == "fine"
