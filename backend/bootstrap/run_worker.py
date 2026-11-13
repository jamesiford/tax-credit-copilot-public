"""Starts the run worker: as its own process (`python -m bootstrap.run_worker`) or as a thread inside the API. [ADR-012]

This is composition, so it lives in `bootstrap`: it names the real repository and the real collaborators that the
framework-free worker (`application/runs/worker.py`) is deliberately not allowed to import.

Two ways to run it, and the difference matters:

* **Its own process** (the deployed shape). Any number of processes may run; the queue's leases keep them from
  taking the same item, and the per-client rule keeps them from running one client twice.
* **Inline in the API** (`RUN_WORKER_INLINE`, on by default only for `ENVIRONMENT=local`). One thread, convenient for a
  laptop. In a deployed API that scales out, every instance would start one, so it is a single-instance trial setting
  and logs a warning saying so.
"""
from __future__ import annotations

import argparse
import logging
import signal
import threading
from typing import Any

import bootstrap.wiring  # noqa: F401 - binds every service the worker's commands ask for
from application.deployment import is_deployed, store_choice
from application.runs.executor import ItemExecutor
from application.runs.worker import RunWorker
from bootstrap.run_batch_wiring import get_run_batch_repository
from config import get_settings

log = logging.getLogger("tcc.runs")


def build_worker() -> RunWorker:
    """A worker over the configured queue, calling the existing commands through the mediator."""
    return RunWorker(get_run_batch_repository(), ItemExecutor(), get_settings().runs)


class InlineWorker:
    """A handle on the in-process worker with the `done`/`cancel` shape the API's start-up tasks share."""

    def __init__(self, thread: threading.Thread, stop: threading.Event) -> None:
        self._thread, self._stop = thread, stop

    def done(self) -> bool:
        return not self._thread.is_alive()

    def cancel(self) -> None:
        self._stop.set()


def start_inline_worker() -> InlineWorker | None:
    """Start the in-process worker when `RUN_WORKER_INLINE` says so; None when it is off."""
    if not get_settings().runs.worker_inline:
        return None
    if is_deployed():
        log.warning(
            "RUN_WORKER_INLINE is on in a deployed process. This is for a single-instance trial: if the API scales "
            "out, every instance runs a worker. Deploy the worker as its own process instead (RUN-ORCHESTRATION.md)."
        )
    stop = threading.Event()
    thread = threading.Thread(target=build_worker().run_forever, args=(stop,), name="run-worker-inline", daemon=True)
    thread.start()
    log.info("inline run worker started")
    return InlineWorker(thread, stop)


def _warn_if_private_queue() -> None:
    if store_choice("RUN_MANIFEST_STORE") == "memory":
        log.warning(
            "RUN_MANIFEST_STORE=memory: the queue is private to this process, so it cannot see batches started by the "
            "API. Use RUN_MANIFEST_STORE=sqlite locally, or warehouse when deployed."
        )


def main(argv: list[str] | None = None) -> int:
    """Run until stopped (SIGINT or SIGTERM), or with `--once` until the queue is empty."""
    parser = argparse.ArgumentParser(description="Run orchestration worker: leases and runs queued client runs.")
    parser.add_argument("--once", action="store_true", help="work until nothing is claimable, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _warn_if_private_queue()
    worker = build_worker()
    if args.once:
        done = worker.drain()
        log.info("run worker drained: %d item(s) claimed", done)
        return 0
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    log.info("run worker %s started", worker.owner)
    worker.run_forever(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
