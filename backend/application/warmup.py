"""Paying the cold-read cost before the first screen asks for it.

A cold lakehouse is slow in a way that has nothing to do with the calculation:
`/api/scope` alone has been measured at 58 seconds and then a connect timeout,
and the landing grid at 99 seconds for the reference client. Every one of those
seconds is spent on the first request after a restart, which is exactly when
somebody is watching.

The engine is deterministic and payroll is immutable for a run, so the caches
these reads fill are safe to fill early. This runs in a background thread after
startup: it never blocks the app coming up, and every step is guarded so a
lakehouse that is unreachable degrades to a slow first request rather than a
dead API.

Skipped unless `DATA_SOURCE=lakehouse`, because the cost being avoided is network
latency. Under `csv` the same work is a local file read, and making the test
suite pay for it would be a poor trade.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

log = logging.getLogger("tax-credit-copilot")


def should_warm() -> bool:
    from tools.fabric_source import active_data_source

    if os.getenv("TCC_WARM_ON_START", "1").strip().lower() in ("0", "false", "no"):
        return False
    return active_data_source() == "lakehouse"


def keepalive_interval_s() -> int:
    """How often to touch the pool. Must stay under the ODBC 60s idle timeout.

    30s is the measured safe point: a connection is still hot after 30s idle
    (120ms) and dead after 90s (3,216ms).
    """
    try:
        return max(5, int(os.getenv("TCC_KEEPALIVE_SECONDS", "30")))
    except ValueError:
        return 30


def touch_warehouse() -> int:
    """Keep the pooled warehouse connections from timing out.

    Gated on `should_warm()` for the same reason the warm-up is: tests and CI
    have no warehouse, and a background task that opens one would turn an
    offline suite into a flaky one.
    """
    if not should_warm():
        return 0
    from application.wiring import get_gold_reader

    return get_gold_reader().connection.keepalive()


def _reap_stranded_runs() -> int:
    """Mark runs that died with their process failed, so they stop reading live."""
    from infrastructure.persistence.warehouse_gold import GoldWriter

    return GoldWriter().reap_stranded_runs()


def _timed(report: list[dict[str, Any]], step: str, work) -> Any:
    started = time.monotonic()
    try:
        result = work()
    except Exception as exc:
        # A cold Delta log times out rather than failing fast. That is worth a
        # log line and nothing more: the request path retries on its own.
        report.append({
            "step": step,
            "seconds": round(time.monotonic() - started, 1),
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}"[:200],
        })
        log.warning("warm-up step %s failed: %s", step, type(exc).__name__)
        return None
    report.append({
        "step": step,
        "seconds": round(time.monotonic() - started, 1),
        "ok": True,
    })
    return result


def warm_read_paths(*, warm_workspace=None) -> dict[str, Any]:
    """Fill the caches the first screen reads, in the order it reads them.

    `warm_workspace` is injected because the sealed run is a singleton owned by
    the router that serves it, and the application layer does not import
    routers [ADR-003].
    """
    from application.wiring import get_gold_reader
    from data.source.from_fabric import FabricLakehouseReader
    from infrastructure.payroll.pay_period_source import configured_account_id

    report: list[dict[str, Any]] = []
    started = time.monotonic()

    # 0. The connection pool, filled ONE AT A TIME. Concurrent opens against
    #    this warehouse cost 6-7s each; serial ones cost far less, and paying
    #    for them here means the first page borrows instead of building.
    _timed(report, "connections", lambda: get_gold_reader().connection.prewarm())

    # 1. The account table. `/api/scope` blocks the shell's scope selector on it.
    _timed(report, "accounts", lambda: FabricLakehouseReader().list_accounts())

    # 2. Close out runs that died with the process. Nothing in-process can mark
    #    these, because no handler ran; a restart is the first moment anything
    #    can. Until then every page for that client claims a run is in flight.
    _timed(report, "reap_stranded_runs", _reap_stranded_runs)

    # 3. The sealed run. The shell renders nothing until `/api/workspace` answers.
    if warm_workspace is not None:
        _timed(report, "sealed_workspace", warm_workspace)

    # 4. The landing grid. It reads Gold, so the cost to move off the request is
    #    the warehouse connection and its token, not an engine replay.
    account_id = configured_account_id()
    _timed(
        report,
        "trend",
        lambda: get_gold_reader().latest_run(account_id),
    )

    total = round(time.monotonic() - started, 1)
    log.info(
        "warm-up finished in %ss: %s",
        total,
        ", ".join(f"{r['step']}={r['seconds']}s{'' if r['ok'] else ' FAILED'}" for r in report),
    )
    return {"total_seconds": total, "steps": report}
