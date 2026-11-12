"""Counters for every source read: what was read, how much, how long, and whether a cache answered. [08.8]

A read that scales with a whole table is a defect, and a defect nobody can see is not fixed. Every Delta read and every
cache decision is counted here, process-wide and thread-safe, and `snapshot()` is what the readiness endpoint, the benchmark
harness and the regression tests read. Nothing here records a value from the data, only table names and sizes.
"""
from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_TABLES: dict[str, dict[str, Any]] = {}
_CACHE = {"hits": 0, "misses": 0, "negative_hits": 0, "evictions": 0, "single_flight_waits": 0}


def record_read(table: str, rows: int, nbytes: int, columns: int, seconds: float, *, filtered: bool, version: int | None = None) -> None:
    """One Delta read of `table`."""
    with _LOCK:
        t = _TABLES.setdefault(table, {"reads": 0, "rows": 0, "bytes": 0, "seconds": 0.0, "unfiltered_reads": 0, "max_columns": 0, "version": None})
        t["reads"] += 1
        t["rows"] += rows
        t["bytes"] += nbytes
        t["seconds"] = round(t["seconds"] + seconds, 4)
        t["unfiltered_reads"] += 0 if filtered else 1
        t["max_columns"] = max(t["max_columns"], columns)
        t["version"] = version if version is not None else t["version"]


def record_cache(event: str) -> None:
    """`hits`, `misses`, `negative_hits`, `evictions` or `single_flight_waits`."""
    with _LOCK:
        _CACHE[event] += 1


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {"tables": {k: dict(v) for k, v in _TABLES.items()}, "cache": dict(_CACHE),
                "rows": sum(t["rows"] for t in _TABLES.values()), "bytes": sum(t["bytes"] for t in _TABLES.values())}


def reset() -> None:
    with _LOCK:
        _TABLES.clear()
        for key in _CACHE:
            _CACHE[key] = 0
