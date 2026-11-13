"""Row mapping and column lists for the run batch tables (migration 0004), shared by both adapters.

The SQL is portable T-SQL that SQLite also accepts, so one store (`run_batch_store.py`) serves the
Warehouse and local runs; only how a statement is executed and how an instant is bound differ, and
those live in the two thin adapters. [ADR-012]
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from domain.runs import (
    BatchKind, BatchStatus, ItemStatus, RunBatch, RunBatchItem, ScopeKind,
)

BATCH_TABLE = "run_batch"
ITEM_TABLE = "run_batch_item"

BATCH_COLUMNS = (
    "batch_id", "kind", "scope_kind", "scope_spec", "program_code", "tax_years", "force_run",
    "include_code_commit", "refresh_once", "status", "cancel_requested", "items_total", "items_queued",
    "items_running", "items_succeeded", "items_skipped", "items_failed", "items_cancelled", "requested_by",
    "requested_at", "started_at", "finished_at", "idempotency_key", "dry_run_summary",
)
ITEM_COLUMNS = (
    "item_id", "batch_id", "seq", "client_id", "program_code", "tax_year", "status", "attempts", "lease_owner",
    "lease_expires_at", "heartbeat_at", "not_before", "run_id", "skip_reason", "error_dependency",
    "error_message", "started_at", "finished_at",
)

#: Which stored counter each item status feeds. `leased` and `running` share one: to a person watching a
#: batch both mean "being worked on".
COUNTER = {
    "queued": "items_queued", "leased": "items_running", "running": "items_running",
    "succeeded": "items_succeeded", "skipped_unchanged": "items_skipped", "skipped_no_payroll": "items_skipped",
    "failed": "items_failed", "cancelled": "items_cancelled",
}

Bind = Callable[[datetime | None], Any]
Parse = Callable[[Any], datetime | None]


def counters(status_counts: dict[str, int]) -> dict[str, int]:
    out = {name: 0 for name in set(COUNTER.values())}
    for status, n in status_counts.items():
        out[COUNTER[status]] += n
    out["items_total"] = sum(status_counts.values())
    return out


def batch_values(batch: RunBatch, status_counts: dict[str, int], bind: Bind) -> list[Any]:
    c = counters(status_counts)
    return [
        batch.batch_id, batch.kind.value, batch.scope_kind.value, json.dumps(batch.scope_spec, sort_keys=True),
        batch.program_code, json.dumps(list(batch.tax_years)) if batch.tax_years else None, int(batch.force),
        int(batch.include_code_commit), int(batch.refresh_once), batch.status.value, int(batch.cancel_requested),
        c["items_total"], c["items_queued"], c["items_running"], c["items_succeeded"], c["items_skipped"],
        c["items_failed"], c["items_cancelled"], batch.requested_by, bind(batch.requested_at),
        bind(batch.started_at), bind(batch.finished_at), batch.idempotency_key,
        json.dumps(batch.dry_run_summary, sort_keys=True) if batch.dry_run_summary else None,
    ]


def item_values(item: RunBatchItem, bind: Bind) -> list[Any]:
    return [
        item.item_id, item.batch_id, item.seq, item.client_id, item.program_code, item.tax_year, item.status.value,
        item.attempts, item.lease_owner, bind(item.lease_expires_at), bind(item.heartbeat_at), bind(item.not_before),
        item.run_id, item.skip_reason, item.error_dependency, item.error_message, bind(item.started_at),
        bind(item.finished_at),
    ]


def to_batch(row: dict[str, Any], parse: Parse) -> RunBatch:
    """A batch from a stored row; `skip_unchanged` travels in the stored spec, so it needs no column."""
    counts = {k: int(row[k] or 0) for k in (
        "items_total", "items_queued", "items_running", "items_succeeded", "items_skipped", "items_failed",
        "items_cancelled")}
    spec = json.loads(row["scope_spec"] or "{}")
    return RunBatch(
        batch_id=row["batch_id"], kind=BatchKind(row["kind"]), scope_kind=ScopeKind(row["scope_kind"]),
        scope_spec=spec, program_code=row["program_code"], skip_unchanged=bool(spec.get("skip_unchanged")),
        tax_years=tuple(json.loads(row["tax_years"])) if row["tax_years"] else (), force=bool(row["force_run"]),
        include_code_commit=bool(row["include_code_commit"]), refresh_once=bool(row["refresh_once"]),
        status=BatchStatus(row["status"]), cancel_requested=bool(row["cancel_requested"]),
        requested_by=row["requested_by"], requested_at=parse(row["requested_at"]),
        started_at=parse(row["started_at"]), finished_at=parse(row["finished_at"]),
        idempotency_key=row["idempotency_key"],
        dry_run_summary=json.loads(row["dry_run_summary"]) if row["dry_run_summary"] else {}, counts=counts,
    )


def to_item(row: dict[str, Any], parse: Parse) -> RunBatchItem:
    return RunBatchItem(
        item_id=row["item_id"], batch_id=row["batch_id"], seq=int(row["seq"]), client_id=int(row["client_id"]),
        program_code=row["program_code"], tax_year=None if row["tax_year"] is None else int(row["tax_year"]),
        status=ItemStatus(row["status"]), attempts=int(row["attempts"]), lease_owner=row["lease_owner"],
        lease_expires_at=parse(row["lease_expires_at"]), heartbeat_at=parse(row["heartbeat_at"]),
        not_before=parse(row["not_before"]), run_id=row["run_id"], skip_reason=row["skip_reason"],
        error_dependency=row["error_dependency"], error_message=row["error_message"],
        started_at=parse(row["started_at"]), finished_at=parse(row["finished_at"]),
    )


def insert_sql(table: str, columns: tuple[str, ...], rows: int) -> str:
    one = "(" + ", ".join("?" for _ in columns) + ")"
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES " + ", ".join(one for _ in range(rows))
