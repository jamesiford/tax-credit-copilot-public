"""Run batches: start, watch, cancel and retry recalculation for many clients. [ADR-012]

Thin: parse, dispatch through the mediator, shape the answer. The work itself runs in the worker, so none of
these calls waits on an engine run. The existing `POST /api/v2/clients/{id}/runs` and `POST /api/claims/assess`
are unchanged; a batch is the way to run more than one client.

Typed bodies and responses (the first routes in this API to be). A refusal is a 4xx whose `detail` carries
`code`, `reason` and `remedy`, so a client can show what to change without parsing a sentence.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api._rate_limit import rate_limited
from api.auth import attributed
from application.commands.cancel_run_batch import CancelRunBatchCommand
from application.commands.enqueue_run_batch import EnqueueRunBatchCommand
from application.commands.retry_failed_items import RetryFailedItemsCommand
from application.queries.run_batch_reads import (
    GetRunBatchQuery, ListRunBatchesQuery, ListRunBatchItemsQuery, PreviewRunBatchQuery,
)
from application.runs.errors import (
    BatchTooLarge, ConfirmationRequired, RunBatchRefused, UnknownBatch,
)
from application.services import get_mediator

router = APIRouter(prefix="/api/v2/run-batches", tags=["runs"])


class ScopeBody(BaseModel):
    """Which clients: explicit ids, a portfolio filter resolved on the server, or the whole book."""
    kind: Literal["one", "list", "filter", "all"] = "list"
    client_ids: list[int] = Field(default_factory=list, max_length=50_000, description="For kinds one and list.")
    filter: dict[str, Any] = Field(
        default_factory=dict, max_length=12,
        description="For kind filter: program, year, outcome, scope, status, near (the portfolio filters), "
                    "and band, state, unassessed, unavailable.",
    )


class StartBody(BaseModel):
    """A request to run many clients. `dry_run` previews it; confirmation and idempotency fields guard a real start."""
    kind: Literal["assess", "calculate", "assess_and_calculate"] = "calculate"
    scope: ScopeBody
    program_code: str | None = Field(None, max_length=64)
    tax_years: list[int] = Field(default_factory=list, max_length=12, description="Empty: each client's latest runnable year.")
    force: bool = Field(False, description="Run every item even if skip_unchanged is on. Kept for compatibility.")
    skip_unchanged: bool = Field(False, description="Skip clients whose data and rules are unchanged since their last run. Off by default.")
    include_code_commit: bool = False
    refresh_once: bool = Field(True, description="One item per client. Off needs explicit tax_years.")
    idempotency_key: str | None = Field(None, max_length=128)
    override_size_limit: bool = Field(False, description="Allowed for scope kind all only.")
    confirm_items: int | None = Field(None, description="Must equal the item count above the confirmation threshold.")
    dry_run: bool = Field(False, description="Preview only: writes nothing and reads no payroll.")


class Counts(BaseModel):
    """Items by outcome. `running` includes leased items: to a person watching, both mean being worked on."""
    total: int
    queued: int
    running: int
    succeeded: int
    skipped: int
    failed: int
    cancelled: int


class Progress(BaseModel):
    """Items finished (succeeded, skipped, failed or cancelled) out of the total."""
    done: int
    total: int


class DegradedEntry(BaseModel):
    """A dependency that is not answering, with what it affects and what to do (the repository-wide degraded shape)."""
    dependency: str
    impact: str
    remedy: str


class BatchOut(BaseModel):
    """A batch as the portal and the channel read it: status, derived counters and the preview it was started from."""
    batch_id: str
    kind: str
    scope_kind: str
    scope_spec: dict[str, Any]
    program_code: str | None
    tax_years: list[int]
    force: bool
    skip_unchanged: bool = False
    include_code_commit: bool
    refresh_once: bool
    status: str
    cancel_requested: bool
    counts: Counts
    progress: Progress
    requested_by: str
    requested_at: str | None
    started_at: str | None
    finished_at: str | None
    idempotency_key: str | None
    dry_run_summary: dict[str, Any]
    idempotent_replay: bool = False
    degraded: list[DegradedEntry] = Field(default_factory=list)
    cancelled_now: int | None = None
    requeued: int | None = None


class BatchesPage(BaseModel):
    """One page of batches, newest first, with the unfiltered total so a pager can say how many there are."""
    items: list[BatchOut]
    total: int
    limit: int
    offset: int


class ItemOut(BaseModel):
    """One client (and maybe year) in a batch, with why it was skipped or failed."""
    item_id: str
    batch_id: str
    seq: int
    client_id: int
    program_code: str | None
    tax_year: int | None
    status: str
    attempts: int
    run_id: str | None
    skip_reason: str | None
    error_dependency: str | None
    error_message: str | None
    not_before: str | None
    started_at: str | None
    finished_at: str | None


class ItemsPage(BaseModel):
    """One page of a batch's items, in the order they were queued."""
    items: list[ItemOut]
    total: int
    limit: int
    offset: int


class PreviewOut(BaseModel):
    """What a start would do. Carries `dry_run` so a client cannot mistake it for a queued batch."""
    dry_run: bool = True
    preview: dict[str, Any]


def _refused(exc: RunBatchRefused) -> HTTPException:
    status = 409 if isinstance(exc, ConfirmationRequired) else 413 if isinstance(exc, BatchTooLarge) else 422
    return HTTPException(status_code=status, detail=exc.as_detail())


def _send(request: Any) -> Any:
    try:
        return get_mediator().send(request)
    except RunBatchRefused as exc:
        raise _refused(exc) from exc
    except UnknownBatch as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=BatchOut | PreviewOut, status_code=202, dependencies=[Depends(rate_limited("batch_start"))])
def start_run_batch(body: StartBody, request: Request) -> Any:
    """Queue a batch (202), or with `dry_run` say what it would do (nothing is written)."""
    common = dict(
        kind=body.kind, scope_kind=body.scope.kind, client_ids=tuple(body.scope.client_ids), filter=body.scope.filter,
        program_code=body.program_code, tax_years=tuple(body.tax_years), force=body.force,
        skip_unchanged=body.skip_unchanged, include_code_commit=body.include_code_commit, refresh_once=body.refresh_once,
    )
    if body.dry_run:
        return {"dry_run": True, "preview": _send(PreviewRunBatchQuery(**common))}
    return _send(EnqueueRunBatchCommand(
        actor=attributed(request, None, default="anonymous"), idempotency_key=body.idempotency_key,
        override_size_limit=body.override_size_limit, confirm_items=body.confirm_items, **common,
    ))


@router.get("", response_model=BatchesPage)
def list_run_batches(
    limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0), status: str | None = None,
) -> Any:
    return _send(ListRunBatchesQuery(limit=limit, offset=offset, status=status))


@router.get("/{batch_id}", response_model=BatchOut)
def get_run_batch(batch_id: str) -> Any:
    """The batch, its counters, and a degraded `run_worker` entry when queued work has no worker."""
    return _send(GetRunBatchQuery(batch_id=batch_id))


@router.get("/{batch_id}/items", response_model=ItemsPage)
def list_run_batch_items(
    batch_id: str, status: str | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
) -> Any:
    return _send(ListRunBatchItemsQuery(batch_id=batch_id, status=status, limit=limit, offset=offset))


@router.post("/{batch_id}/cancel", response_model=BatchOut)
def cancel_run_batch(batch_id: str, request: Request) -> Any:
    """Cancel what has not started; an item already running finishes."""
    return _send(CancelRunBatchCommand(batch_id=batch_id, actor=attributed(request, None, default="anonymous")))


@router.post("/{batch_id}/retry-failed", response_model=BatchOut)
def retry_failed_items(batch_id: str, request: Request) -> Any:
    """Re-queue the failed items; finished and skipped items are not repeated."""
    return _send(RetryFailedItemsCommand(batch_id=batch_id, actor=attributed(request, None, default="anonymous")))
