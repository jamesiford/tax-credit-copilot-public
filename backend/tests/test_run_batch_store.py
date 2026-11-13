"""The run batch queue: the same behaviour on the SQLite adapter and on the Warehouse adapter (over a fake connection).

The Warehouse adapter is exercised through its real statements and the real `run_in_transaction`, over a SQLite
connection that also injects write conflicts (24556, 3960, 1205). Not proven here, and listed in live-checks.md:
snapshot-isolation behaviour on a live Warehouse.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from domain.runs import (
    BatchKind, BatchStatus, ItemResult, ItemStatus, RunBatch, RunBatchItem, ScopeKind,
)
from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository
from infrastructure.persistence.warehouse_run_batches import WarehouseRunBatchRepository
from tests.ddl_schema import warehouse_tables

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class _FlakyCursor:
    def __init__(self, cursor, owner):
        self._c, self._owner = cursor, owner

    def execute(self, sql, params=()):
        if self._owner.fail_next:
            self._owner.fail_next -= 1
            self._owner.conflicts += 1
            raise RuntimeError(f"[SQL] ({self._owner.error_number}) snapshot isolation transaction aborted")
        sql = sql.replace("tcc_ops.", "")
        sql = re.sub(r"OFFSET \? ROWS FETCH NEXT \? ROWS ONLY", "LIMIT ? OFFSET ?", sql)
        params = [p.isoformat() if isinstance(p, datetime) else p for p in params]
        if "LIMIT ? OFFSET ?" in sql:
            params[-2], params[-1] = params[-1], params[-2]
        self._c.execute(sql, params)
        return self

    def __getattr__(self, name):
        return getattr(self._c, name)


class _FakeConnection:
    """What `FabricWarehouseConnection.connect()` yields: a connection with autocommit, commit and rollback."""

    def __init__(self, schema_sql: str):
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.raw.executescript(schema_sql)
        self.autocommit = True
        self.fail_next = 0
        self.conflicts = 0
        self.error_number = 24556

    def cursor(self):
        return _FlakyCursor(self.raw.cursor(), self)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    @contextmanager
    def connect(self):
        yield self


def _schema() -> str:
    from infrastructure.persistence.sqlite_run_batches import _SCHEMA

    return _SCHEMA


@pytest.fixture(params=["sqlite", "warehouse"])
def repo(request):
    if request.param == "sqlite":
        r = SqliteRunBatchRepository(":memory:")
        r.fail_next = lambda n, number=24556: None
        yield r
        r.close()
        return
    connection = _FakeConnection(_schema())
    r = WarehouseRunBatchRepository(connection)
    r.connection = connection
    yield r


def _batch(**kw) -> RunBatch:
    base = dict(batch_id=uuid.uuid4().hex, kind=BatchKind.CALCULATE, scope_kind=ScopeKind.LIST,
                scope_spec={"client_ids": [1, 2, 3]}, requested_by="tester", requested_at=NOW)
    base.update(kw)
    return RunBatch(**base)


def _items(batch: RunBatch, clients: list[int]) -> list[RunBatchItem]:
    return [RunBatchItem(item_id=f"{batch.batch_id[:6]}-{i:04d}", batch_id=batch.batch_id, client_id=c, seq=i)
            for i, c in enumerate(clients)]


def test_the_migration_and_the_sqlite_schema_name_the_same_columns():
    from infrastructure.persistence import run_batch_rows as rows

    tables = warehouse_tables()
    assert tables["tcc_ops.run_batch"] == list(rows.BATCH_COLUMNS)
    assert tables["tcc_ops.run_batch_item"] == list(rows.ITEM_COLUMNS)


def test_create_and_read_back_with_counters(repo):
    b = _batch()
    created = repo.create(b, _items(b, [1, 2, 3]))
    assert created.counts["items_total"] == 3 and created.counts["items_queued"] == 3
    items, total = repo.list_items(b.batch_id, None, 2, 0)
    assert total == 3 and [i.client_id for i in items] == [1, 2]
    batches, n = repo.list_batches(10, 0)
    assert n == 1 and batches[0].batch_id == b.batch_id


def test_a_claim_takes_one_item_per_client_and_respects_the_limit(repo):
    b = _batch()
    repo.create(b, _items(b, [1, 1, 2, 3]))
    got = repo.claim("w1", 3, 120, NOW)
    assert sorted(i.client_id for i in got) == [1, 2, 3]
    assert all(i.status is ItemStatus.LEASED and i.attempts == 1 for i in got)
    assert repo.claim("w2", 3, 120, NOW) == [], "client 1's second item waits for its first"


def test_a_client_with_a_live_lease_is_not_claimed_by_another_worker(repo):
    b = _batch()
    repo.create(b, _items(b, [7, 7]))
    first = repo.claim("w1", 1, 120, NOW)
    assert len(first) == 1
    assert repo.claim("w2", 1, 120, NOW + timedelta(seconds=60)) == []
    repo.finish(first[0].item_id, "w1", NOW, ItemResult(ItemStatus.SUCCEEDED, run_id="r1"))
    second = repo.claim("w2", 1, 120, NOW + timedelta(seconds=61))
    assert [i.client_id for i in second] == [7]


def test_an_expired_lease_returns_to_the_queue_and_then_fails_when_attempts_are_spent(repo):
    b = _batch()
    repo.create(b, _items(b, [5]))
    repo.claim("dead", 1, 10, NOW)
    later = NOW + timedelta(seconds=30)
    assert repo.reap_expired(later, max_attempts=2) == [b.batch_id]
    assert repo.get_item(_items(b, [5])[0].item_id).status is ItemStatus.QUEUED
    repo.claim("dead2", 1, 10, later)
    repo.reap_expired(later + timedelta(seconds=30), max_attempts=2)
    item = repo.get_item(_items(b, [5])[0].item_id)
    assert item.status is ItemStatus.FAILED and item.error_dependency == "worker"


def test_heartbeat_extends_only_the_owners_lease(repo):
    b = _batch()
    repo.create(b, _items(b, [5]))
    item = repo.claim("w1", 1, 10, NOW)[0]
    assert repo.heartbeat(item.item_id, "w1", 10, NOW + timedelta(seconds=5)) is True
    assert repo.heartbeat(item.item_id, "intruder", 10, NOW) is False


def test_requeue_waits_for_the_backoff(repo):
    b = _batch()
    repo.create(b, _items(b, [5]))
    item = repo.claim("w1", 1, 120, NOW)[0]
    repo.requeue(item.item_id, "w1", NOW + timedelta(seconds=60), "warehouse", "boom")
    assert repo.claim("w1", 1, 120, NOW + timedelta(seconds=10)) == []
    assert len(repo.claim("w1", 1, 120, NOW + timedelta(seconds=61))) == 1


def test_cancel_stops_queued_items_but_not_running_ones(repo):
    b = _batch()
    repo.create(b, _items(b, [1, 2, 3]))
    running = repo.claim("w1", 1, 120, NOW)[0]
    assert repo.cancel(b.batch_id, NOW) == 2
    assert repo.get_item(running.item_id).status is ItemStatus.LEASED
    assert repo.claim("w2", 5, 120, NOW) == []
    repo.finish(running.item_id, "w1", NOW, ItemResult(ItemStatus.SUCCEEDED))
    assert repo.refresh(b.batch_id, NOW).status is BatchStatus.PARTIAL


def test_retry_failed_requeues_only_failed_items(repo):
    b = _batch()
    repo.create(b, _items(b, [1, 2]))
    a, c = repo.claim("w1", 2, 120, NOW)
    repo.finish(a.item_id, "w1", NOW, ItemResult(ItemStatus.FAILED, error_dependency="validation", error_message="no"))
    repo.finish(c.item_id, "w1", NOW, ItemResult(ItemStatus.SUCCEEDED))
    assert repo.refresh(b.batch_id, NOW).status is BatchStatus.PARTIAL
    assert repo.retry_failed(b.batch_id, NOW) == 1
    assert repo.get_item(a.item_id).attempts == 0
    assert repo.refresh(b.batch_id, NOW).status is BatchStatus.RUNNING


def test_idempotency_lookup_is_per_requester(repo):
    b = _batch(idempotency_key="k1")
    repo.create(b, _items(b, [1]))
    assert repo.find_by_key("k1", "tester").batch_id == b.batch_id
    assert repo.find_by_key("k1", "someone-else") is None


def test_queue_health_reports_queued_and_live_leases(repo):
    b = _batch()
    repo.create(b, _items(b, [1, 2]))
    assert repo.queue_health(NOW)["queued"] == 2 and repo.queue_health(NOW)["live_leases"] == 0
    repo.claim("w1", 1, 120, NOW)
    health = repo.queue_health(NOW)
    assert health["queued"] == 1 and health["live_leases"] == 1


@pytest.mark.parametrize("number", [24556, 3960, 1205])
def test_the_warehouse_adapter_retries_a_write_conflict(number):
    connection = _FakeConnection(_schema())
    connection.error_number = number
    r = WarehouseRunBatchRepository(connection)
    b = _batch()
    connection.fail_next = 2
    r.create(b, _items(b, [1, 2]))
    assert connection.conflicts == 2
    assert r.get(b.batch_id).counts["items_total"] == 2
