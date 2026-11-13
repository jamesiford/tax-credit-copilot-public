"""Who may see which part of a run batch. [F07.3]

A batch names clients (its scope, its items, its error text). The read side used to show every batch to every signed-in caller,
so a caller entitled to two clients could read the others' ids and errors. The rule now: a caller sees only the items of
clients the client authorizer lets it act for, the counters and status are recomputed over that view, a batch with nothing the
caller may see does not exist for it (an unknown batch, never a 403, so existence does not leak), and the scope's client list
and the dry-run summary (which names clients) are narrowed.

With the default authorizer (`AllClientsAuthorizer`, every authenticated caller sees every client) nothing is filtered and the
stored batch is returned as it always was, so behaviour without an employer binding is unchanged.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Callable

from application.identity import ANONYMOUS, AllClientsAuthorizer, ambient_principal
from application.runs.errors import UnknownBatch
from domain.runs import RunBatch, RunBatchItem, batch_status

_PAGE = 500
#: Item status -> the counter a batch carries for it (the same grouping the store uses).
_COUNTER = {
    "queued": "items_queued", "leased": "items_running", "running": "items_running", "succeeded": "items_succeeded",
    "skipped_unchanged": "items_skipped", "skipped_no_payroll": "items_skipped", "failed": "items_failed", "cancelled": "items_cancelled",
}


def visible_clients() -> Callable[[int], bool] | None:
    """A predicate for the clients the ambient caller may act for, or None when nobody is restricted."""
    from application.services import get_client_authorizer

    authorizer = get_client_authorizer()
    if isinstance(authorizer, AllClientsAuthorizer):
        return None
    principal = ambient_principal() or ANONYMOUS
    return lambda client_id: authorizer.is_authorized(principal, client_id)


def all_items(repo: Any, batch_id: str) -> list[RunBatchItem]:
    items: list[RunBatchItem] = []
    while True:
        page, total = repo.list_items(batch_id, None, _PAGE, len(items))
        items += page
        if not page or len(items) >= total:
            return items


def _narrowed_scope(spec: dict[str, Any], allowed: set[int]) -> dict[str, Any]:
    out = dict(spec)
    if isinstance(out.get("client_ids"), list):
        out["client_ids"] = [c for c in out["client_ids"] if c in allowed]
    if "client_count" in out:
        out["client_count"] = len(allowed)
    return out


def narrowed(batch: RunBatch, items: list[RunBatchItem], can_see: Callable[[int], bool]) -> RunBatch | None:
    """The batch as the caller may see it, or None when none of its clients are the caller's."""
    mine = [i for i in items if can_see(i.client_id)]
    if not mine:
        return None
    by_status = Counter(i.status.value for i in mine)
    counts = {name: 0 for name in set(_COUNTER.values())}
    for status, n in by_status.items():
        counts[_COUNTER[status]] += n
    counts["items_total"] = len(mine)
    return replace(
        batch, counts=counts, status=batch_status(dict(by_status), cancel_requested=batch.cancel_requested),
        scope_spec=_narrowed_scope(batch.scope_spec, {i.client_id for i in mine}), dry_run_summary={},
    )


def one_batch(repo: Any, batch_id: str, can_see: Callable[[int], bool]) -> tuple[RunBatch, list[RunBatchItem]]:
    batch = repo.get(batch_id)
    if batch is None:
        raise UnknownBatch(batch_id)
    items = all_items(repo, batch_id)
    view = narrowed(batch, items, can_see)
    if view is None:
        raise UnknownBatch(batch_id)
    return view, [i for i in items if can_see(i.client_id)]


def page_of_batches(repo: Any, limit: int, offset: int, status: str | None, can_see: Callable[[int], bool]) -> tuple[list[RunBatch], int]:
    """Newest first. The status filter applies to the caller's own view, so it is checked after narrowing."""
    seen: list[RunBatch] = []
    start = 0
    while True:
        page, total = repo.list_batches(200, start, None)
        for batch in page:
            view = narrowed(batch, all_items(repo, batch.batch_id), can_see)
            if view is not None and (status is None or view.status.value == status):
                seen.append(view)
        start += len(page)
        if not page or start >= total:
            return seen[offset:offset + limit], len(seen)
