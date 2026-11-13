"""Process-wide counters for run batches, read by the readiness probe and the operator. [ADR-012]

Deliberately tiny: a dict of integers behind a lock. The structured log line each item writes carries the detail
(batch, client, year, outcome, duration, dependency); these answer "how is this process doing" without a log query.
"""
from __future__ import annotations

import threading
from collections import Counter
from typing import Any

_lock = threading.Lock()
_counts: Counter[str] = Counter()
_durations: dict[str, float] = {}


def record(outcome: str, *, seconds: float = 0.0, dependency: str | None = None) -> None:
    with _lock:
        _counts[f"items.{outcome}"] += 1
        _durations["items.seconds_total"] = _durations.get("items.seconds_total", 0.0) + seconds
        if dependency:
            _counts[f"failures.{dependency}"] += 1


def event(name: str) -> None:
    with _lock:
        _counts[name] += 1


def snapshot() -> dict[str, Any]:
    with _lock:
        return {**dict(_counts), **{k: round(v, 3) for k, v in _durations.items()}}


def reset() -> None:
    with _lock:
        _counts.clear()
        _durations.clear()
