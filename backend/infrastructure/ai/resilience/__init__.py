"""Layer the resilience decorators over one provider. [AI-04]

Order, outermost first:  bulkhead → breaker → retry → timeout → call.
(The egress and budget guards sit outside this, in `application/ai/guarded.py`.)

The order is the design. The BULKHEAD is outside the breaker so shedding load is not
counted as the provider failing. The BREAKER is outside retry so one request that
retries three times is one failure, not three — and an open breaker stops retries
being attempted at all. RETRY is outside TIMEOUT so a timed-out attempt is retried.
"""
from __future__ import annotations

import random
from typing import Any

from application.ai.settings import ResilienceSettings
from infrastructure.ai.resilience.breaker import BreakerRuntime, CircuitBreaker
from infrastructure.ai.resilience.bulkhead import BulkheadRuntime
from infrastructure.ai.resilience.clock import Clock, RealClock
from infrastructure.ai.resilience.retry import RetryRuntime
from infrastructure.ai.resilience.timeout import TimeoutRuntime

__all__ = ["build_resilient_runtime", "BreakerRuntime", "BulkheadRuntime", "RetryRuntime", "TimeoutRuntime", "CircuitBreaker"]


def build_resilient_runtime(
    runtime: Any, policy: ResilienceSettings, *, clock: Clock | None = None,
    rng: random.Random | None = None, telemetry: Any = None,
) -> BulkheadRuntime:
    """`runtime` wrapped in the four decorators, in the order above."""
    clock = clock or RealClock()
    timed = TimeoutRuntime(runtime, policy.call_timeout_s, clock)
    retried = RetryRuntime(timed, policy, clock, rng, telemetry)
    broken = BreakerRuntime(retried, CircuitBreaker(policy.breaker_failures, policy.breaker_reset_s, clock), telemetry)
    return BulkheadRuntime(broken, policy.bulkhead_limit, telemetry)
