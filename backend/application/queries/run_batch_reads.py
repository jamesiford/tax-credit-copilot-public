"""Read run batches: one with its worker health, a page of them, a page of one batch's items, and the preview. [ADR-012]

One module for four small reads because they share one rule: a read changes nothing and reads no payroll. The
worker health is the `run_worker` degraded dependency: queued items with nothing leasing them past a threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from application.errors import DependencyUnavailable
from application.mediator import Query
from application.runs.errors import UnknownBatch
from application.runs.plan import BatchRequest, preview
from application.runs.selection import Scope
from application.runs.views import batch_view, item_view
from domain.runs import BatchKind, ScopeKind


def worker_degraded(health: dict[str, Any], stale_seconds: int, now: datetime) -> list[dict[str, Any]]:
    """A degraded entry when work is waiting and no worker has leased anything for `stale_seconds`."""
    oldest = health.get("oldest_queued_at")
    if not health.get("queued") or health.get("live_leases") or oldest is None:
        return []
    waited = (now - oldest).total_seconds()
    if waited < stale_seconds:
        return []
    failure = DependencyUnavailable(
        "run_worker", f"{health['queued']} item(s) have waited {int(waited)} seconds and no worker holds a lease.",
        "Start the worker (python -m bootstrap.run_worker), or set RUN_WORKER_INLINE=true on a single-instance trial.",
        impact="queued runs are not progressing",
    )
    return [failure.as_degraded()]


@dataclass(frozen=True)
class GetRunBatchQuery(Query):
    """One batch with its worker health."""
    batch_id: str = ""


@dataclass(frozen=True)
class ListRunBatchesQuery(Query):
    """A page of batches, newest first, optionally one status."""
    limit: int = 25
    offset: int = 0
    status: str | None = None


@dataclass(frozen=True)
class ListRunBatchItemsQuery(Query):
    """A page of one batch's items, optionally one status."""
    batch_id: str = ""
    status: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class PreviewRunBatchQuery(Query):
    """What a start would do, from the same fields a start takes; writes nothing."""
    kind: str = BatchKind.CALCULATE.value
    scope_kind: str = ScopeKind.LIST.value
    client_ids: tuple[int, ...] = ()
    filter: dict[str, Any] = field(default_factory=dict)
    program_code: str | None = None
    tax_years: tuple[int, ...] = ()
    force: bool = False
    skip_unchanged: bool = False
    include_code_commit: bool = False
    refresh_once: bool = True


def handle_get_run_batch(query: GetRunBatchQuery) -> dict[str, Any]:
    from application.services import get_run_batch_repository
    from config import get_settings

    repo, now = get_run_batch_repository(), datetime.now(timezone.utc)
    batch = repo.get(query.batch_id)
    if batch is None:
        raise UnknownBatch(query.batch_id)
    degraded = worker_degraded(repo.queue_health(now), get_settings().runs.stale_worker_seconds, now)
    return {**batch_view(batch), "degraded": degraded}


def handle_list_run_batches(query: ListRunBatchesQuery) -> dict[str, Any]:
    from application.services import get_run_batch_repository

    items, total = get_run_batch_repository().list_batches(max(1, min(query.limit, 200)), max(0, query.offset), query.status)
    return {"items": [batch_view(b) for b in items], "total": total, "limit": query.limit, "offset": query.offset}


def handle_list_run_batch_items(query: ListRunBatchItemsQuery) -> dict[str, Any]:
    from application.services import get_run_batch_repository

    repo = get_run_batch_repository()
    if repo.get(query.batch_id) is None:
        raise UnknownBatch(query.batch_id)
    items, total = repo.list_items(query.batch_id, query.status, max(1, min(query.limit, 500)), max(0, query.offset))
    return {"items": [item_view(i) for i in items], "total": total, "limit": query.limit, "offset": query.offset}


def handle_preview_run_batch(query: PreviewRunBatchQuery) -> dict[str, Any]:
    from config import get_settings

    request = BatchRequest(
        kind=BatchKind(query.kind), scope=Scope(ScopeKind(query.scope_kind), tuple(query.client_ids), dict(query.filter)),
        program_code=query.program_code, tax_years=tuple(query.tax_years), force=query.force,
        skip_unchanged=query.skip_unchanged, include_code_commit=query.include_code_commit, refresh_once=query.refresh_once,
    )
    return preview(request, get_settings().runs)
