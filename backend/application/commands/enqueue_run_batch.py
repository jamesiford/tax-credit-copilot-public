"""Start a run batch: assess and/or calculate a set of clients as tracked work. [ADR-012]

A **command**: it queues work that will change what the business believes, so it needs a writer, an actor and an
audit record. It does the cheap part now (resolve the clients, check limits and confirmation, store the items) and
leaves every calculation to the worker, so nothing here blocks on an engine run.

Starting the same request twice returns the first batch: by `idempotency_key` when one is given, and otherwise by
an identical request that is still queued or running.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from application.identity import Policy
from application.mediator import Command
from application.runs.errors import ConfirmationRequired
from application.runs.plan import BatchRequest, check_size, item_count, make_items, preview, spec_for
from application.runs.selection import Scope, resolve_clients
from application.runs.views import batch_view
from domain.runs import BatchKind, RunBatch, ScopeKind


@dataclass(frozen=True)
class EnqueueRunBatchCommand(Command):
    """The request to start a batch, as plain fields so the channel and the API build it the same way."""
    kind: str = BatchKind.CALCULATE.value
    scope_kind: str = ScopeKind.LIST.value
    client_ids: tuple[int, ...] = ()
    filter: dict[str, Any] = field(default_factory=dict)
    program_code: str | None = None
    tax_years: tuple[int, ...] = ()
    force: bool = False
    include_code_commit: bool = False
    refresh_once: bool = True
    idempotency_key: str | None = None
    override_size_limit: bool = False
    confirm_items: int | None = None
    policy = Policy.WRITER

    def request(self) -> BatchRequest:
        return BatchRequest(
            kind=BatchKind(self.kind), scope=Scope(ScopeKind(self.scope_kind), tuple(self.client_ids), dict(self.filter)),
            program_code=self.program_code, tax_years=tuple(self.tax_years), force=self.force,
            include_code_commit=self.include_code_commit, refresh_once=self.refresh_once,
            idempotency_key=self.idempotency_key, override_size_limit=self.override_size_limit,
            confirm_items=self.confirm_items,
        ).validated()


def _stored_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """The preview without its sample rows: the column is 4000 characters and the rows are in the items."""
    return {k: v for k, v in summary.items() if k != "first_items"}


def handle_enqueue_run_batch(command: EnqueueRunBatchCommand) -> dict[str, Any]:
    """Resolve, check limits and confirmation, dedupe, then store the batch and its items."""
    from application.services import get_run_batch_repository
    from config import get_settings

    settings = get_settings().runs
    request, repo = command.request(), get_run_batch_repository()
    if request.idempotency_key:
        earlier = repo.find_by_key(request.idempotency_key, command.actor)
        if earlier is not None:
            return batch_view(earlier, replay=True)

    resolution = resolve_clients(request.scope)
    items = item_count(len(resolution.client_ids), request)
    check_size(items, request, settings)
    if items > settings.confirm_above and request.confirm_items != items:
        raise ConfirmationRequired(items, settings.confirm_above)

    spec = spec_for(request, resolution.client_ids)
    open_twin = repo.find_open_identical(request.kind.value, json.dumps(spec, sort_keys=True), command.actor)
    if open_twin is not None:
        return batch_view(open_twin, replay=True)

    batch = RunBatch(
        batch_id=uuid.uuid4().hex, kind=request.kind, scope_kind=request.scope.kind, scope_spec=spec,
        requested_by=command.actor, requested_at=datetime.now(timezone.utc), program_code=request.program_code,
        tax_years=request.tax_years, force=request.force, include_code_commit=request.include_code_commit,
        refresh_once=request.refresh_once, idempotency_key=request.idempotency_key,
        dry_run_summary=_stored_summary(preview(request, settings, resolution=resolution)),
    )
    created = repo.create(batch, make_items(batch.batch_id, resolution.client_ids, request))
    return batch_view(created)
