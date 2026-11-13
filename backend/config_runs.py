"""Run orchestration settings: batch limits, worker sizing and lease timing. [ADR-012]

Defaults are conservative: one item at a time (Gold writes can conflict on the Warehouse and the per-client lock there is only narrowed, not airtight), three
attempts for a transient failure, and a lease long enough for a slow run but short enough that a dead worker's
items come back within minutes. `RUN_WORKER_INLINE` defaults on only for `ENVIRONMENT=local`: an in-process worker
in a deployed API that scales out would run the same item on several instances.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from config_values import optional_flag, tuned_int


@dataclass(frozen=True)
class RunSettings:
    """Limits, sizing and lease timing for run batches, with conservative defaults."""
    max_items: int = 5000
    confirm_above: int = 25
    worker_concurrency: int = 1
    item_max_attempts: int = 3
    worker_inline: bool = False
    lease_seconds: int = 120
    heartbeat_seconds: int = 30
    poll_seconds: int = 5
    stale_worker_seconds: int = 300
    backoff_base_seconds: int = 5


def parse_runs(environ: Mapping[str, str]) -> RunSettings:
    """`RUN_BATCH_MAX_ITEMS`, `RUN_BATCH_CONFIRM_ABOVE`, `RUN_WORKER_CONCURRENCY` (1-8), `RUN_ITEM_MAX_ATTEMPTS`,
    `RUN_WORKER_INLINE`, `RUN_LEASE_SECONDS`, `RUN_HEARTBEAT_SECONDS`, `RUN_WORKER_POLL_SECONDS`,
    `RUN_WORKER_STALE_SECONDS`, `RUN_BACKOFF_BASE_SECONDS`."""
    local = (environ.get("ENVIRONMENT") or "local").strip().lower() == "local"
    inline = optional_flag(environ, "RUN_WORKER_INLINE")
    lease = tuned_int(environ, "RUN_LEASE_SECONDS", 120, 15)
    return RunSettings(
        max_items=tuned_int(environ, "RUN_BATCH_MAX_ITEMS", 5000, 1),
        confirm_above=tuned_int(environ, "RUN_BATCH_CONFIRM_ABOVE", 25, 1),
        worker_concurrency=min(8, tuned_int(environ, "RUN_WORKER_CONCURRENCY", 1, 1)),
        item_max_attempts=tuned_int(environ, "RUN_ITEM_MAX_ATTEMPTS", 3, 1),
        worker_inline=local if inline is None else inline,
        lease_seconds=lease,
        heartbeat_seconds=min(tuned_int(environ, "RUN_HEARTBEAT_SECONDS", 30, 5), max(5, lease // 2)),
        poll_seconds=tuned_int(environ, "RUN_WORKER_POLL_SECONDS", 5, 1),
        stale_worker_seconds=tuned_int(environ, "RUN_WORKER_STALE_SECONDS", 300, 30),
        backoff_base_seconds=tuned_int(environ, "RUN_BACKOFF_BASE_SECONDS", 5, 1),
    )
