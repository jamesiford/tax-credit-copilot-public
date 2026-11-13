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
import json
import logging
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bootstrap.wiring  # noqa: F401 - binds every service the worker's commands ask for
from application.deployment import is_deployed, store_choice
from application.runs import metrics
from application.runs.executor import ItemExecutor
from application.runs.worker import RunWorker
from bootstrap.run_batch_wiring import get_run_batch_repository
from config import get_settings, use_managed_identity

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


class _Health(BaseHTTPRequestHandler):
    """`GET /healthz`: alive, with this process's counters. The platform only needs the 200."""

    def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
        body = json.dumps({"status": "ok", "counters": metrics.snapshot()}).encode()
        self.send_response(200 if self.path.rstrip("/") == "/healthz" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Probes every few seconds would drown the worker's own log."""


def serve_health(port: int) -> ThreadingHTTPServer:
    """Answer the platform's health probe on `port` in a daemon thread; the worker has no other HTTP surface."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _Health)
    threading.Thread(target=server.serve_forever, name="run-worker-health", daemon=True).start()
    return server


def _warn_if_private_queue() -> None:
    if store_choice("RUN_MANIFEST_STORE") == "memory":
        log.warning(
            "RUN_MANIFEST_STORE=memory: the queue is private to this process, so it cannot see batches started by the "
            "API. Use RUN_MANIFEST_STORE=sqlite locally, or warehouse when deployed."
        )


def apply_worker_identity() -> bool:
    """Run this PROCESS as its own managed identity when `RUN_WORKER_IDENTITY_CLIENT_ID` is set; True when it did.

    One identity stays the default (the worker shares the API's grants). A separate identity lets an operator give the worker
    only what a run needs (RUN-ORCHESTRATION.md lists it). The SDK selects a user-assigned identity from `AZURE_CLIENT_ID`, so
    this sets it for this process before any credential is built. It never applies to the inline worker, which is the API's
    own process and has no identity of its own.
    """
    client_id = get_settings().runs.worker_identity_client_id
    if not client_id:
        return False
    use_managed_identity(client_id)
    log.info("run worker uses its own managed identity (client id ending ...%s)", client_id[-4:])
    return True


def main(argv: list[str] | None = None) -> int:
    """Run until stopped (SIGINT or SIGTERM), or with `--once` until the queue is empty."""
    parser = argparse.ArgumentParser(description="Run orchestration worker: leases and runs queued client runs.")
    parser.add_argument("--once", action="store_true", help="work until nothing is claimable, then exit")
    parser.add_argument("--health-port", type=int, default=0, help="serve /healthz on this port (App Service's PORT)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    apply_worker_identity()
    _warn_if_private_queue()
    worker = build_worker()
    if args.health_port:
        serve_health(args.health_port)
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
