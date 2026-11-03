"""A per-user token bucket. [CH-06]

`CHANNEL_RATE_LIMIT_PER_MINUTE` calls a minute per key, refilled continuously, so a
burst up to the limit is allowed and a steady stream above it is refused with the
number of seconds until a call would pass. PER PROCESS: with more than one worker
each holds its own bucket, so the effective ceiling is the limit times
`WEB_CONCURRENCY`. That is stated in the runbook, not hidden.

A bounded table: a stream of distinct keys cannot grow it without limit, since the
buckets least recently used are dropped first (and a dropped bucket only means that
key starts full again).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable

MAX_KEYS = 10_000


class RateLimiter:
    """`allow(key)` -> `(True, 0)` or `(False, seconds_to_wait)`."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        if per_minute < 1:
            raise ValueError("the rate limit must allow at least one call a minute")
        self._capacity, self._rate, self._clock = float(per_minute), per_minute / 60.0, clock
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """Spend one token for `key` if there is one."""
        now = self._clock()
        with self._lock:
            tokens, stamp = self._buckets.pop(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - stamp) * self._rate)
            allowed = tokens >= 1.0
            self._buckets[key] = (tokens - 1.0 if allowed else tokens, now)
            while len(self._buckets) > MAX_KEYS:
                self._buckets.popitem(last=False)
        return (True, 0) if allowed else (False, max(1, int((1.0 - tokens) / self._rate) + 1))
