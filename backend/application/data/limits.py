"""Limits that keep data queries from slowing the shared warehouse. [CH-16c]

The Fabric capacity here is small and shared with every page load and every calculation run,
so a data tool that can be called in a loop is a way to degrade the product. Three guards, and
each REFUSES rather than queues, because a queued query is exactly the load being avoided:

- **A per-person budget** (`allow(key) -> (bool, wait_seconds)`, the gateway's token bucket).
- **A concurrency bulkhead**: at most N data queries in flight across all people; the next one
  is refused as `query_busy` after a short wait, not held.
- **Timeout and row caps** carried in `QueryLimits` and applied by the adapters and the service.

All per process: with several workers the effective ceiling is the figure times the worker
count, which the runbook states rather than hides.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from application.data.exec_errors import QueryBusy
from application.data.spec import MAX_LIMIT

DEFAULT_TIMEOUT_S = 20.0
DEFAULT_RATE_PER_MINUTE = 30
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_BUSY_WAIT_S = 0.25


@dataclass(frozen=True, slots=True)
class QueryLimits:
    """The numbers a data query runs under. `hard_max_rows` can only lower a spec's own limit (<= 500)."""

    timeout_s: float = DEFAULT_TIMEOUT_S
    hard_max_rows: int = MAX_LIMIT
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    busy_wait_s: float = DEFAULT_BUSY_WAIT_S

    def __post_init__(self) -> None:
        if self.timeout_s <= 0 or self.max_concurrency < 1 or not 1 <= self.hard_max_rows <= MAX_LIMIT:
            raise ValueError("data query limits out of range")

    def rows_for(self, requested: int) -> int:
        """The rows this query may return: its own limit, never above the server cap."""
        return min(requested, self.hard_max_rows)


class QueryBudget(Protocol):
    """What the service needs of a rate limiter: `allow(key)` -> `(allowed, seconds_to_wait)`."""

    def allow(self, key: str) -> tuple[bool, int]:
        """Spend one query for `key` if there is one."""
        ...


class Bulkhead:
    """A bounded number of data queries in flight, refusing rather than queueing the rest."""

    def __init__(self, max_concurrency: int, wait_s: float = DEFAULT_BUSY_WAIT_S) -> None:
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._wait_s = wait_s

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one slot for the duration of a query, or raise `QueryBusy` if none frees up quickly."""
        if not self._slots.acquire(timeout=self._wait_s):
            raise QueryBusy("data queries are busy right now; try again in a few seconds")
        try:
            yield
        finally:
            self._slots.release()
