"""How run batches and items look on the wire: plain dicts of strings, numbers and ISO instants. [ADR-012]"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.runs import RunBatch, RunBatchItem


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def batch_view(batch: RunBatch, *, replay: bool = False) -> dict[str, Any]:
    """A batch as a plain dict, with progress derived from the counters."""
    c = batch.counts
    done = sum(c.get(k, 0) for k in ("items_succeeded", "items_skipped", "items_failed", "items_cancelled"))
    return {
        "batch_id": batch.batch_id, "kind": batch.kind.value, "scope_kind": batch.scope_kind.value,
        "scope_spec": batch.scope_spec, "program_code": batch.program_code, "tax_years": list(batch.tax_years),
        "force": batch.force, "include_code_commit": batch.include_code_commit, "refresh_once": batch.refresh_once,
        "status": batch.status.value, "cancel_requested": batch.cancel_requested,
        "counts": {
            "total": c.get("items_total", 0), "queued": c.get("items_queued", 0), "running": c.get("items_running", 0),
            "succeeded": c.get("items_succeeded", 0), "skipped": c.get("items_skipped", 0),
            "failed": c.get("items_failed", 0), "cancelled": c.get("items_cancelled", 0),
        },
        "progress": {"done": done, "total": c.get("items_total", 0)},
        "requested_by": batch.requested_by, "requested_at": _iso(batch.requested_at),
        "started_at": _iso(batch.started_at), "finished_at": _iso(batch.finished_at),
        "idempotency_key": batch.idempotency_key, "dry_run_summary": batch.dry_run_summary,
        "idempotent_replay": replay,
    }


def item_view(item: RunBatchItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id, "batch_id": item.batch_id, "seq": item.seq, "client_id": item.client_id,
        "program_code": item.program_code, "tax_year": item.tax_year, "status": item.status.value,
        "attempts": item.attempts, "run_id": item.run_id, "skip_reason": item.skip_reason,
        "error_dependency": item.error_dependency, "error_message": item.error_message,
        "not_before": _iso(item.not_before), "started_at": _iso(item.started_at), "finished_at": _iso(item.finished_at),
    }
