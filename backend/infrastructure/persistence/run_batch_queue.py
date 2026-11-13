"""Queue operations on run batch items: claim, heartbeat, finish, requeue, reap, health. [ADR-012]

Mixed into `RunBatchStore` (see that module for the backend contract and why the per-client lock is a
tie-break after an optimistic claim). Every statement is written to be safe to re-run from the top,
because on the Warehouse a write conflict re-runs the whole transaction.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from domain.runs import ItemResult, RunBatchItem
from infrastructure.persistence import run_batch_rows as rows
from infrastructure.persistence.run_batch_store import _ACTIVE, RunBatchStore, Tx

_ACTIVE_SQL = ", ".join(f"'{s}'" for s in _ACTIVE)
_ITEM_SELECT = ", ".join(f"i.{c}" for c in rows.ITEM_COLUMNS)


def _items_in(tx: Tx, backend: Any, table: str, item_ids: list[str]) -> list[RunBatchItem]:
    """The items as stored, in the order given, read in the claiming transaction (no second round trip per item)."""
    if not item_ids:
        return []
    marks = ", ".join("?" for _ in item_ids)
    found = {r["item_id"]: rows.to_item(r, backend.parse) for r in tx.execute(
        f"SELECT {', '.join(rows.ITEM_COLUMNS)} FROM {table} WHERE item_id IN ({marks})", item_ids).rows}
    return [found[i] for i in item_ids if i in found]


class QueueOps:
    """Mixin: the methods a worker needs."""

    _b: Any
    _item: str
    _batch: str

    def _live_lock_holder(self, tx: Tx, client_id: int, now: datetime) -> str | None:
        found = tx.execute(
            f"SELECT MIN(item_id) AS holder FROM {self._item} WHERE client_id = ? AND status IN ({_ACTIVE_SQL}) "
            "AND lease_expires_at > ?", [client_id, self._b.bind(now)]).rows
        return found[0]["holder"] if found else None

    def claim(self, owner: str, limit: int, lease_seconds: int, now: datetime) -> list[RunBatchItem]:
        """Lease up to `limit` queued items, at most one per client and none for a client already leased."""
        expires = now + timedelta(seconds=lease_seconds)

        def work(tx: Tx) -> list[RunBatchItem]:
            """Pick candidates, flip them to leased, and keep only the per-client lock holders."""
            # A client with a live lease is excluded in the query itself (one statement, and the candidate window holds only
            # claimable items); `busy` then covers the clients taken in this very claim.
            busy: set[int] = set()
            clause, extra = self._b.page(limit * 20 + 20, 0)
            candidates = tx.execute(
                f"SELECT i.item_id, i.client_id FROM {self._item} i JOIN {self._batch} b ON b.batch_id = i.batch_id "
                "WHERE i.status = 'queued' AND b.cancel_requested = 0 AND (i.not_before IS NULL OR i.not_before <= ?) "
                f"AND NOT EXISTS (SELECT 1 FROM {self._item} x WHERE x.client_id = i.client_id AND x.status IN ({_ACTIVE_SQL}) "
                f"AND x.lease_expires_at > ?) ORDER BY b.requested_at, i.seq, i.item_id {clause}",
                [self._b.bind(now), self._b.bind(now), *extra]).rows
            taken: list[tuple[str, int]] = []
            for cand in candidates:
                if len(taken) >= limit:
                    break
                if cand["client_id"] in busy:
                    continue
                won = tx.execute(
                    f"UPDATE {self._item} SET status = 'leased', lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?, "
                    "attempts = attempts + 1 WHERE item_id = ? AND status = 'queued'",
                    [owner, self._b.bind(expires), self._b.bind(now), cand["item_id"]]).rowcount
                if won == 1:
                    taken.append((cand["item_id"], cand["client_id"]))
                    busy.add(cand["client_id"])
            kept = self._keep_lock_holders(tx, taken, owner, now)
            return _items_in(tx, self._b, self._item, kept)

        return self._b.transact(work)

    def _keep_lock_holders(self, tx: Tx, taken: list[tuple[str, int]], owner: str, now: datetime) -> list[str]:
        kept: list[str] = []
        for item_id, client_id in taken:
            if self._live_lock_holder(tx, client_id, now) == item_id:
                kept.append(item_id)
            else:
                tx.execute(
                    f"UPDATE {self._item} SET status = 'queued', lease_owner = NULL, lease_expires_at = NULL, "
                    "attempts = attempts - 1 WHERE item_id = ? AND lease_owner = ?", [item_id, owner])
        return kept

    def get_item(self, item_id: str) -> RunBatchItem | None:
        found = self._b.transact(lambda tx: tx.execute(
            f"SELECT {', '.join(rows.ITEM_COLUMNS)} FROM {self._item} WHERE item_id = ?", [item_id]).rows)
        return rows.to_item(found[0], self._b.parse) if found else None

    def heartbeat(self, item_id: str, owner: str, lease_seconds: int, now: datetime) -> bool:
        """Extend the lease. False means it is no longer ours (expired and reclaimed, or cancelled)."""
        return self._b.transact(lambda tx: tx.execute(
            f"UPDATE {self._item} SET heartbeat_at = ?, lease_expires_at = ? WHERE item_id = ? AND lease_owner = ? "
            f"AND status IN ({_ACTIVE_SQL})",
            [self._b.bind(now), self._b.bind(now + timedelta(seconds=lease_seconds)), item_id, owner]).rowcount) == 1

    def mark_running(self, item_id: str, owner: str, tax_year: int | None, program_code: str | None, now: datetime) -> bool:
        return self._b.transact(lambda tx: tx.execute(
            f"UPDATE {self._item} SET status = 'running', started_at = ?, tax_year = ?, program_code = ? "
            "WHERE item_id = ? AND lease_owner = ? AND status = 'leased'",
            [self._b.bind(now), tax_year, program_code, item_id, owner]).rowcount) == 1

    def finish(self, item_id: str, owner: str, now: datetime, result: ItemResult, *, refresh_batch: str | None = None) -> bool:
        """Record how the item ended and release its lease. False means the lease was no longer ours.

        With `refresh_batch` the batch's counters are recomputed in the same transaction (one round trip fewer per item, and
        the counters can never be read out of step with the item that was just finished).
        """
        def work(tx: Tx) -> bool:
            kept = tx.execute(
                f"UPDATE {self._item} SET status = ?, finished_at = ?, run_id = ?, skip_reason = ?, error_dependency = ?, "
                "error_message = ?, tax_year = COALESCE(?, tax_year), lease_owner = NULL, lease_expires_at = NULL "
                f"WHERE item_id = ? AND lease_owner = ? AND status IN ({_ACTIVE_SQL})",
                [result.status.value, self._b.bind(now), result.run_id, result.skip_reason, result.error_dependency,
                 (result.error_message or "")[:1000] or None, result.tax_year, item_id, owner]).rowcount == 1
            if refresh_batch:
                self.refresh_in(tx, refresh_batch, now)  # type: ignore[attr-defined]
            return kept

        return self._b.transact(work)

    def requeue(
        self, item_id: str, owner: str, not_before: datetime, error_dependency: str | None, error_message: str | None,
    ) -> bool:
        """Give the item back for another attempt after `not_before` (a transient failure with attempts left)."""
        return self._b.transact(lambda tx: tx.execute(
            f"UPDATE {self._item} SET status = 'queued', not_before = ?, error_dependency = ?, error_message = ?, "
            "lease_owner = NULL, lease_expires_at = NULL "
            f"WHERE item_id = ? AND lease_owner = ? AND status IN ({_ACTIVE_SQL})",
            [self._b.bind(not_before), error_dependency, (error_message or "")[:1000] or None, item_id, owner]).rowcount) == 1

    def release(self, item_id: str, owner: str) -> bool:
        """Hand a claim back untouched (the attempt did not happen)."""
        return self._b.transact(lambda tx: tx.execute(
            f"UPDATE {self._item} SET status = 'queued', lease_owner = NULL, lease_expires_at = NULL, "
            f"attempts = attempts - 1 WHERE item_id = ? AND lease_owner = ? AND status IN ({_ACTIVE_SQL})",
            [item_id, owner]).rowcount) == 1

    def reap_expired(self, now: datetime, max_attempts: int) -> list[str]:
        """Items whose lease lapsed: a dead worker's. Back to `queued`, or `failed` once attempts are spent.

        Returns the affected batch ids so the caller can refresh their counters.
        """
        def work(tx: Tx) -> list[str]:
            """Find lapsed leases and requeue or fail each; one transaction so a conflict re-runs all of it."""
            lapsed = tx.execute(
                f"SELECT item_id, batch_id, attempts FROM {self._item} WHERE status IN ({_ACTIVE_SQL}) "
                "AND lease_expires_at < ?", [self._b.bind(now)]).rows
            for r in lapsed:
                spent = int(r["attempts"]) >= max_attempts
                tx.execute(
                    f"UPDATE {self._item} SET status = ?, lease_owner = NULL, lease_expires_at = NULL, "
                    "error_dependency = 'worker', error_message = 'the worker stopped before finishing this item', "
                    "finished_at = ? WHERE item_id = ? AND status IN (" + _ACTIVE_SQL + ") AND lease_expires_at < ?",
                    ["failed" if spent else "queued", self._b.bind(now) if spent else None, r["item_id"], self._b.bind(now)])
            return sorted({r["batch_id"] for r in lapsed})

        return self._b.transact(work)

    def queue_health(self, now: datetime) -> dict[str, Any]:
        """What a status page needs to say whether anything is working the queue."""
        def work(tx: Tx) -> dict[str, Any]:
            """Count waiting items and live leases in one transaction."""
            q = tx.execute(f"SELECT COUNT(*) AS n, MIN(b.requested_at) AS oldest FROM {self._item} i JOIN {self._batch} b "
                           "ON b.batch_id = i.batch_id WHERE i.status = 'queued' AND b.cancel_requested = 0").rows[0]
            live = tx.execute(f"SELECT COUNT(*) AS n, MAX(heartbeat_at) AS last FROM {self._item} WHERE status IN "
                              f"({_ACTIVE_SQL}) AND lease_expires_at > ?", [self._b.bind(now)]).rows[0]
            return {"queued": int(q["n"]), "oldest_queued_at": self._b.parse(q["oldest"]),
                    "live_leases": int(live["n"]), "last_heartbeat_at": self._b.parse(live["last"])}

        return self._b.transact(work)


class RunBatchRepository(QueueOps, RunBatchStore):
    """The whole port: batches, items and the queue."""
