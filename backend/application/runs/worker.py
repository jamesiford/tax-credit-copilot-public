"""The run worker: leases queued items, runs them through the executor, heartbeats, retries, recovers. [ADR-012]

Framework-free and clock-injected, so the whole life of an item (claim, run, retry with backoff, lease expiry, cancel)
is tested without threads sleeping. The entry points that compose it with the real stores are
`bootstrap/run_worker.py` (`python -m bootstrap.run_worker`) and `scripts/run-worker.py`; the application layer may not
import the composition root, so it cannot start itself.

Concurrency is bounded twice: at most `RUN_WORKER_CONCURRENCY` items in flight, and never two items of one client
(the claim enforces it). A cancel is honoured between items: an item that already started finishes.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from typing import Any

from application.runs import metrics
from application.runs.executor import ItemExecutor, ItemOutcome
from config import RunSettings
from domain.runs import ItemResult, ItemStatus, RunBatchItem, backoff_seconds

log = logging.getLogger("tcc.runs")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunWorker:
    """Claims, runs, heartbeats and recovers items; one instance per worker process."""
    def __init__(
        self, repo: Any, executor: ItemExecutor, settings: RunSettings, *, owner: str | None = None,
        clock: Callable[[], datetime] = _utcnow, jitter: Callable[[], float] | None = None,
    ) -> None:
        self._repo, self._executor, self._s, self._clock = repo, executor, settings, clock
        self.owner = owner or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._jitter = jitter or (lambda: 0.0)
        self._pool = ThreadPoolExecutor(max_workers=settings.worker_concurrency, thread_name_prefix="run-item")
        self._inflight: dict[str, Future] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ one cycle

    def tick(self) -> int:
        """Reap lapsed leases, claim into free slots, start them. Returns how many items were claimed."""
        now = self._clock()
        self._collect()
        for batch_id in self._repo.reap_expired(now, self._s.item_max_attempts):
            self._repo.refresh(batch_id, now)
            metrics.event("leases.reaped")
        free = self._s.worker_concurrency - len(self._inflight)
        claimed = self._repo.claim(self.owner, free, self._s.lease_seconds, now) if free > 0 else []
        for item in claimed:
            self._inflight[item.item_id] = self._pool.submit(self._process, item)
        return len(claimed)

    def _collect(self) -> None:
        for item_id in [i for i, f in self._inflight.items() if f.done()]:
            self._inflight.pop(item_id).result()

    def heartbeat(self) -> None:
        """Extend the lease of everything in flight. A lost lease is logged; the executor's finish will be refused."""
        for item_id in list(self._inflight):
            if not self._repo.heartbeat(item_id, self.owner, self._s.lease_seconds, self._clock()):
                log.warning("run item %s lost its lease", item_id)

    def drain(self) -> int:
        """Work until nothing is claimable and nothing is in flight. Used by tests and `--once`."""
        total = 0
        while True:
            n = self.tick()
            total += n
            if self._inflight:
                wait(list(self._inflight.values()), return_when=FIRST_COMPLETED, timeout=self._s.poll_seconds)
            elif not n:
                return total

    def run_forever(self, stop: threading.Event) -> None:
        beat = threading.Thread(target=self._beat, args=(stop,), name="run-heartbeat", daemon=True)
        beat.start()
        while not stop.is_set():
            try:
                if not self.tick():
                    stop.wait(self._s.poll_seconds)
            except Exception:  # noqa: BLE001 - a store outage must not kill the loop; the next tick retries
                log.exception("run worker tick failed")
                stop.wait(self._s.poll_seconds)
        self._pool.shutdown(wait=True)

    def _beat(self, stop: threading.Event) -> None:
        while not stop.wait(self._s.heartbeat_seconds):
            try:
                self.heartbeat()
            except Exception:  # noqa: BLE001
                log.exception("run worker heartbeat failed")

    # ------------------------------------------------------------------ one item

    def _process(self, item: RunBatchItem) -> None:
        started = time.monotonic()
        batch = self._repo.get(item.batch_id)
        if batch is None or batch.cancel_requested:
            self._finish(item, ItemOutcome(ItemStatus.CANCELLED, skip_reason="the batch was cancelled"), started)
            return
        outcome = self._executor.execute(
            batch, item, on_target=lambda year, program: self._repo.mark_running(
                item.item_id, self.owner, year, program, self._clock()),
        )
        if self._should_retry(item, outcome):
            delay = backoff_seconds(item.attempts, base=self._s.backoff_base_seconds, jitter=self._jitter)
            self._repo.requeue(item.item_id, self.owner, self._clock() + timedelta(seconds=delay),
                               outcome.error_dependency, outcome.error_message)
            metrics.record("retried", seconds=time.monotonic() - started, dependency=outcome.error_dependency)
            log.warning("run item %s will retry in %.0fs (%s)", item.item_id, delay, outcome.error_dependency)
            self._repo.refresh(item.batch_id, self._clock())
            return
        self._finish(item, outcome, started)

    def _should_retry(self, item: RunBatchItem, outcome: ItemOutcome) -> bool:
        """A transient failure gets the configured attempts. A Gold write that did not validate gets exactly one more.

        The retry is a requeue, and a claim never gives a client to two workers, so the second attempt runs with no
        other worker holding the client. A second failure stays failed and visible in the batch. [F04b.3]
        """
        if outcome.status is not ItemStatus.FAILED:
            return False
        if outcome.retry_once:
            return item.attempts == 1
        return outcome.transient and item.attempts < self._s.item_max_attempts

    def _finish(self, item: RunBatchItem, outcome: ItemOutcome, started: float) -> None:
        now = self._clock()
        kept = self._repo.finish(item.item_id, self.owner, now, outcome.result())
        seconds = time.monotonic() - started
        metrics.record(outcome.status.value, seconds=seconds,
                       dependency=outcome.error_dependency if outcome.status is ItemStatus.FAILED else None)
        log.info(
            "run item finished", extra={
                "batch_id": item.batch_id, "client_id": item.client_id, "tax_year": outcome.tax_year,
                "outcome": outcome.status.value, "seconds": round(seconds, 2), "dependency": outcome.error_dependency,
                "lease_kept": kept, "transient": outcome.transient,
            })
        self._repo.refresh(item.batch_id, now)
