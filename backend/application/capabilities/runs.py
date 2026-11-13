"""`run_batch_status` and `run_batch_list`: how run batches are going, for the channel. [ADR-012]

Reads of the same queue the portal's Runs page reads, through the same queries, so the channel, the page and the
API cannot say different things about one batch. Every figure is the platform's (a count the queue holds); nothing is
computed here. A store that cannot answer is `unavailable`, never "no batches".
"""
from __future__ import annotations

from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.errors import NotCalculated

_SOURCE = "run batch queue"


def _counts_table(counts: dict[str, int]) -> Any:
    rows = [(label, s.cell(counts[key], "count")) for label, key in (
        ("Queued", "queued"), ("Running", "running"), ("Succeeded", "succeeded"), ("Skipped", "skipped"),
        ("Failed", "failed"), ("Cancelled", "cancelled"))]
    return s.table(("Outcome", "Items"), rows)


def _failures(batch_id: str, failed: int) -> list[dict[str, Any]]:
    """The first few failed items, grouped by cause, so a reader can say what went wrong without paging."""
    if not failed:
        return []
    from application.queries.run_batch_reads import ListRunBatchItemsQuery
    from application.services import get_mediator

    page = get_mediator().send(ListRunBatchItemsQuery(batch_id=batch_id, status="failed", limit=50))
    groups: dict[str, dict[str, Any]] = {}
    for item in page["items"]:
        key = item["error_dependency"] or "unknown"
        group = groups.setdefault(key, {"dependency": key, "count": 0, "message": item["error_message"]})
        group["count"] += 1
    return sorted(groups.values(), key=lambda g: -g["count"])


def run_batch_status(batch_id: str | None = None) -> ToolResult:
    """One batch, by id, or the latest when none is named."""
    from application.queries.run_batch_reads import GetRunBatchQuery, ListRunBatchesQuery
    from application.runs.errors import UnknownBatch
    from application.services import get_mediator

    mediator = get_mediator()
    if not batch_id:
        latest = mediator.send(ListRunBatchesQuery(limit=1))["items"]
        if not latest:
            raise NotCalculated("No run batch has been started yet.")
        batch_id = latest[0]["batch_id"]
    try:
        batch = mediator.send(GetRunBatchQuery(batch_id=batch_id))
    except UnknownBatch as exc:
        raise NotCalculated(str(exc)) from exc
    failures = _failures(batch_id, batch["counts"]["failed"])
    facts = {**batch, "failures": failures}
    progress = batch["progress"]
    blocks = [
        s.heading(f"Run batch: {batch['status']}"),
        s.paragraph(
            f"{s.cell(progress['done'], 'count')} of {s.cell(progress['total'], 'count')} runs finished. "
            f"Started by {batch['requested_by']}; kind {batch['kind'].replace('_', ' ')}."
        ),
        _counts_table(batch["counts"]),
    ]
    blocks += [s.paragraph(f"{g['count']} failed with {g['dependency']}: {g['message']}") for g in failures]
    warnings = [f"{d['dependency']}: {d['impact']} {d['remedy']}" for d in batch.get("degraded") or []]
    return s.result("run_batch_status", facts, blocks, provenance=Provenance(source=_SOURCE), warnings=warnings)


def run_batch_list(limit: int = 5, status: str | None = None) -> ToolResult:
    """The most recent batches, newest first."""
    from application.queries.run_batch_reads import ListRunBatchesQuery
    from application.services import get_mediator

    page = get_mediator().send(ListRunBatchesQuery(limit=limit, status=status))
    if not page["items"]:
        raise NotCalculated("No run batch has been started yet." if not status else f"No run batch is {status}.")
    rows = [
        (b["batch_id"][:8], b["kind"].replace("_", " "), b["status"],
         f"{s.cell(b['progress']['done'], 'count')} of {s.cell(b['progress']['total'], 'count')}", b["requested_by"])
        for b in page["items"]
    ]
    blocks = [
        s.heading("Recent run batches"),
        s.table(("Batch", "Kind", "Status", "Done", "Started by"), rows),
    ]
    return s.result("run_batch_list", page, blocks, provenance=Provenance(source=_SOURCE))
