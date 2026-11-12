"""A bounded cache with a memory budget, and single-flight loading. [08.5]

The dataset cache used to be an unbounded process-lifetime dict: one entry per account ever read, each a full dataset, so a
book of thousands of accounts is a memory leak with a long fuse. This replaces it with a least-recently-used cache bounded by
an ESTIMATED byte budget and an entry count, and adds single-flight loading so concurrent requests for the same account share
one read instead of each paying for it (the request that arrives second waits for the first).

Unknown accounts are cached negatively for a short time: asking for an id that does not exist used to repeat the whole read
every time.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable

from . import read_stats

#: Rough bytes per in-memory row of each kind, for the budget. An estimate on purpose: the budget bounds growth, it does not
#: account for every byte, and a conservative figure only means the cache holds fewer accounts.
_BYTES_PER_PAYROLL_ROW = 700
_BYTES_PER_OTHER_ROW = 400


def estimate_bytes(dataset: Any) -> int:
    """An estimate of a `SourceDataset`'s footprint from its row counts."""
    payroll = len(getattr(dataset, "payroll", ()))
    other = sum(len(getattr(dataset, name, ())) for name in (
        "entities", "locations", "addresses", "state_county_zips", "employments", "pay_codes", "pay_frequencies", "fiscal_year_rules"))
    return payroll * _BYTES_PER_PAYROLL_ROW + other * _BYTES_PER_OTHER_ROW


class BoundedCache:
    """LRU by recency, bounded by entry count and by estimated bytes. Thread-safe."""

    def __init__(self, max_entries: int, max_bytes: int, sizeof: Callable[[Any], int] = estimate_bytes) -> None:
        self.max_entries, self.max_bytes, self._sizeof = max_entries, max_bytes, sizeof
        self._items: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            found = self._items.get(key)
            if found is None:
                return None
            self._items.move_to_end(key)
            return found[0]

    def put(self, key: Hashable, value: Any, *, supersedes: Callable[[Hashable], bool] | None = None) -> None:
        """Store `value`; entries `supersedes(k)` calls stale (an older data version of the same account) are dropped first."""
        size = self._sizeof(value)
        with self._lock:
            for old in [k for k in self._items if supersedes and supersedes(k)]:
                del self._items[old]
            self._items[key] = (value, size)
            self._items.move_to_end(key)
            while len(self._items) > 1 and (len(self._items) > self.max_entries or self.total_bytes() > self.max_bytes):
                self._items.popitem(last=False)
                read_stats.record_cache("evictions")

    def total_bytes(self) -> int:
        return sum(size for _, size in self._items.values())

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def keys(self) -> list[Hashable]:
        with self._lock:
            return list(self._items)


class NegativeCache:
    """Remembers "this id does not exist" for `ttl` seconds."""

    def __init__(self, ttl: float) -> None:
        self.ttl, self._seen, self._lock = ttl, {}, threading.Lock()

    def has(self, key: Hashable) -> bool:
        with self._lock:
            stamp = self._seen.get(key)
            if stamp is None or time.monotonic() - stamp > self.ttl:
                self._seen.pop(key, None)
                return False
            return True

    def add(self, key: Hashable) -> None:
        with self._lock:
            self._seen[key] = time.monotonic()

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()


class _Flight:
    """One in-flight load, and what it produced."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.ok = False
        self.value: Any = None


class SingleFlight:
    """Concurrent callers of the same key share one execution of `load`; the others wait for its result (or its error)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[Hashable, _Flight] = {}

    def do(self, key: Hashable, load: Callable[[], Any]) -> Any:
        with self._lock:
            flight = self._running.get(key)
            leader = flight is None
            if leader:
                flight = self._running[key] = _Flight()
        if not leader:
            read_stats.record_cache("single_flight_waits")
            flight.done.wait()
            if flight.ok:
                return flight.value
            raise flight.value
        try:
            flight.value, flight.ok = load(), True
            return flight.value
        except BaseException as exc:  # noqa: BLE001 - waiters get the leader's failure, then it propagates
            flight.value = exc
            raise
        finally:
            with self._lock:
                self._running.pop(key, None)
            flight.done.set()
