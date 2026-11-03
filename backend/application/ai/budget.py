"""A daily token ceiling, overall and per person. [AI-04]

A model call costs money and an unbounded loop (a client script, a retry storm, a
curious user) costs a lot of it. The budget refuses a call BEFORE it is made when
the day's allowance would be crossed, and records what each call actually used.

- Buckets are per UTC day; the first call on a new day starts fresh.
- A ceiling that is `None` is no ceiling: the default is to enforce nothing.
- Provider usage is used when the model reported it; otherwise it is ESTIMATED at
  four characters per token and the record says so, because an estimate presented
  as a measurement is how a bill ends up disagreeing with a dashboard.
- In memory and per process. With several workers the effective ceiling is the
  ceiling times the worker count; a shared store is the follow-up if a customer
  needs it exact. The limit is a guard rail, not an invoice.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

from domain.ai import BudgetExceeded, ModelUsage

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Tokens in `text`, at four characters each, never zero for non-empty text."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class InMemoryTokenBudget:
    """The `TokenBudget` port in memory: one lock, one day's counters, reset when the UTC date changes."""

    def __init__(
        self, global_daily: int | None, principal_daily: int | None, today: Callable[[], str] = _utc_day,
    ) -> None:
        self._global_limit, self._principal_limit, self._today = global_daily, principal_daily, today
        self._lock = threading.Lock()
        self._day = today()
        self._global = 0
        self._by_principal: dict[str, int] = defaultdict(int)

    def _roll(self) -> None:
        day = self._today()
        if day != self._day:
            self._day, self._global = day, 0
            self._by_principal.clear()

    def check(self, principal: str, estimated_tokens: int) -> None:
        with self._lock:
            self._roll()
            if self._global_limit is not None and self._global + estimated_tokens > self._global_limit:
                raise BudgetExceeded("overall", self._global_limit)
            if self._principal_limit is not None and self._by_principal[principal] + estimated_tokens > self._principal_limit:
                raise BudgetExceeded("per-user", self._principal_limit)

    def record(self, principal: str, usage: ModelUsage) -> None:
        total = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        with self._lock:
            self._roll()
            self._global += total
            self._by_principal[principal] += total

    def used(self, principal: str | None = None) -> int:
        with self._lock:
            self._roll()
            return self._global if principal is None else self._by_principal[principal]
