"""The run batch queue, written once over a small backend so the Warehouse and SQLite cannot drift. [ADR-012]

A backend supplies: `table(name)` (schema-qualified where needed), `bind`/`parse` for instants,
and `transact(work)`: run `work(tx)` in one transaction, retrying a write conflict on the Warehouse.
`tx.execute(sql, params)` returns an object with `.rows` (dicts) and `.rowcount`.

Claiming is optimistic: pick candidates, then flip each with `UPDATE ... WHERE status = 'queued'` and
believe only a rowcount of 1. Fabric has no row locks to take, so the per-client rule ("one live lease per
client") is enforced by a deterministic tie-break after the flip: of two items of one client that hold a
live lease, the lower `item_id` keeps it and the other gives its claim back. That narrows the race on a
snapshot-isolated store rather than closing it (LIVE-CHECK-REQUIRED); the executor also refuses to start
while the client has a young `running` manifest, and the section 9 sweep catches a mixed write.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Protocol, TypeVar

from domain.runs import ACTIVE_ITEMS, ItemStatus, RunBatch, RunBatchItem, batch_status
from infrastructure.persistence import run_batch_rows as rows

T = TypeVar("T")
_CHUNK = 50  # rows per INSERT: 50 x 24 columns stays under the 2100-parameter ceiling
_ACTIVE = tuple(s.value for s in ACTIVE_ITEMS)


class Result(Protocol):
    """What a statement returns: its rows as dicts and its row count."""
    rows: list[dict[str, Any]]
    rowcount: int


class Tx(Protocol):
    """A transaction in progress; one statement at a time."""
    def execute(self, sql: str, params: list[Any] | tuple = ()) -> Result: ...


class Backend(Protocol):
    """What an adapter supplies: names, instant encoding, paging and a transaction."""
    def table(self, name: str) -> str: ...
    def bind(self, value: datetime | None) -> Any: ...
    def parse(self, value: Any) -> datetime | None: ...
    def page(self, limit: int, offset: int) -> tuple[str, list[int]]: ...
    def transact(self, work: Callable[[Tx], T]) -> T: ...


class RunBatchStore:
    """`RunBatchRepository` over any `Backend`."""

    is_durable = True

    def __init__(self, backend: Backend) -> None:
        self._b = backend
        self._batch, self._item = backend.table(rows.BATCH_TABLE), backend.table(rows.ITEM_TABLE)

    # ------------------------------------------------------------------ create and read

    def create(self, batch: RunBatch, items: list[RunBatchItem]) -> RunBatch:
        counts: dict[str, int] = {}
        for item in items:
            counts[item.status.value] = counts.get(item.status.value, 0) + 1

        def work(tx: Tx) -> None:
            tx.execute(rows.insert_sql(self._batch, rows.BATCH_COLUMNS, 1), rows.batch_values(batch, counts, self._b.bind))
            for i in range(0, len(items), _CHUNK):
                chunk = items[i:i + _CHUNK]
                flat = [v for it in chunk for v in rows.item_values(it, self._b.bind)]
                tx.execute(rows.insert_sql(self._item, rows.ITEM_COLUMNS, len(chunk)), flat)

        self._b.transact(work)
        return self.get(batch.batch_id)  # type: ignore[return-value]

    def get(self, batch_id: str) -> RunBatch | None:
        found = self._b.transact(lambda tx: tx.execute(
            f"SELECT {', '.join(rows.BATCH_COLUMNS)} FROM {self._batch} WHERE batch_id = ?", [batch_id]).rows)
        return rows.to_batch(found[0], self._b.parse) if found else None

    def find_by_key(self, key: str, requested_by: str) -> RunBatch | None:
        found = self._b.transact(lambda tx: tx.execute(
            f"SELECT {', '.join(rows.BATCH_COLUMNS)} FROM {self._batch} "
            "WHERE idempotency_key = ? AND requested_by = ? ORDER BY requested_at", [key, requested_by]).rows)
        return rows.to_batch(found[0], self._b.parse) if found else None

    def find_open_identical(self, kind: str, spec_json: str, requested_by: str) -> RunBatch | None:
        found = self._b.transact(lambda tx: tx.execute(
            f"SELECT {', '.join(rows.BATCH_COLUMNS)} FROM {self._batch} WHERE kind = ? AND scope_spec = ? "
            "AND requested_by = ? AND status IN ('queued', 'running') ORDER BY requested_at",
            [kind, spec_json, requested_by]).rows)
        return rows.to_batch(found[0], self._b.parse) if found else None

    def list_batches(self, limit: int, offset: int, status: str | None = None) -> tuple[list[RunBatch], int]:
        where, params = ("WHERE status = ?", [status]) if status else ("", [])

        def work(tx: Tx) -> tuple[list[dict], int]:
            total = tx.execute(f"SELECT COUNT(*) AS n FROM {self._batch} {where}", params).rows[0]["n"]
            clause, extra = self._b.page(limit, offset)
            page = tx.execute(
                f"SELECT {', '.join(rows.BATCH_COLUMNS)} FROM {self._batch} {where} "
                f"ORDER BY requested_at DESC, batch_id {clause}", [*params, *extra]).rows
            return page, int(total)

        page, total = self._b.transact(work)
        return [rows.to_batch(r, self._b.parse) for r in page], total

    def list_items(self, batch_id: str, status: str | None, limit: int, offset: int) -> tuple[list[RunBatchItem], int]:
        where, params = "WHERE batch_id = ?", [batch_id]
        if status:
            where, params = where + " AND status = ?", [*params, status]

        def work(tx: Tx) -> tuple[list[dict], int]:
            total = tx.execute(f"SELECT COUNT(*) AS n FROM {self._item} {where}", params).rows[0]["n"]
            clause, extra = self._b.page(limit, offset)
            page = tx.execute(
                f"SELECT {', '.join(rows.ITEM_COLUMNS)} FROM {self._item} {where} "
                f"ORDER BY seq, item_id {clause}", [*params, *extra]).rows
            return page, int(total)

        page, total = self._b.transact(work)
        return [rows.to_item(r, self._b.parse) for r in page], total

    def status_counts(self, batch_id: str) -> dict[str, int]:
        found = self._b.transact(lambda tx: tx.execute(
            f"SELECT status, COUNT(*) AS n FROM {self._item} WHERE batch_id = ? GROUP BY status", [batch_id]).rows)
        return {r["status"]: int(r["n"]) for r in found}

    # ------------------------------------------------------------------ batch status

    def refresh(self, batch_id: str, now: datetime) -> RunBatch:
        """Recompute the stored counters and the status from the items. Idempotent."""
        batch = self.get(batch_id)
        status_counts = self.status_counts(batch_id)
        status = batch_status(status_counts, cancel_requested=batch.cancel_requested)
        c = rows.counters(status_counts)
        done = status.value in ("succeeded", "partial", "failed", "cancelled")
        started = batch.started_at or (now if status.value != "queued" else None)
        finished = (batch.finished_at or now) if done else None

        def work(tx: Tx) -> None:
            tx.execute(
                f"UPDATE {self._batch} SET status = ?, items_total = ?, items_queued = ?, items_running = ?, "
                "items_succeeded = ?, items_skipped = ?, items_failed = ?, items_cancelled = ?, started_at = ?, "
                "finished_at = ? WHERE batch_id = ?",
                [status.value, c["items_total"], c["items_queued"], c["items_running"], c["items_succeeded"],
                 c["items_skipped"], c["items_failed"], c["items_cancelled"], self._b.bind(started),
                 self._b.bind(finished), batch_id])

        self._b.transact(work)
        return self.get(batch_id)  # type: ignore[return-value]

    def cancel(self, batch_id: str, now: datetime) -> int:
        """Stop what has not started. A leased or running item finishes: a half-written run is never abandoned."""
        def work(tx: Tx) -> int:
            tx.execute(f"UPDATE {self._batch} SET cancel_requested = 1 WHERE batch_id = ?", [batch_id])
            return tx.execute(
                f"UPDATE {self._item} SET status = 'cancelled', finished_at = ? "
                "WHERE batch_id = ? AND status = 'queued'", [self._b.bind(now), batch_id]).rowcount

        cancelled = self._b.transact(work)
        self.refresh(batch_id, now)
        return int(cancelled)

    def retry_failed(self, batch_id: str, now: datetime) -> int:
        def work(tx: Tx) -> int:
            n = tx.execute(
                f"UPDATE {self._item} SET status = 'queued', attempts = 0, not_before = NULL, error_dependency = NULL, "
                "error_message = NULL, finished_at = NULL, lease_owner = NULL, lease_expires_at = NULL "
                "WHERE batch_id = ? AND status = 'failed'", [batch_id]).rowcount
            if n:
                tx.execute(f"UPDATE {self._batch} SET cancel_requested = 0, finished_at = NULL WHERE batch_id = ?", [batch_id])
            return n

        n = self._b.transact(work)
        self.refresh(batch_id, now)
        return int(n)
