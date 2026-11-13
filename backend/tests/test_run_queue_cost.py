"""What a run item costs the queue, in statements and transactions, and the behaviour the cheaper queue must keep. [F07.4]

On a Warehouse every statement and every transaction is a round trip, so the counts are the cost. The figures are for the SQLite
stand-in (`scripts/run-batch-scale-check.py` prints them); they say how many round trips the code makes, not how long each takes.
"""
from __future__ import annotations

from datetime import timedelta

from domain.runs import ItemResult, ItemStatus
from tests.test_run_orchestration import NOW, _Clock, _Env, _enqueue, _worker, repo  # noqa: F401 - fixture

#: Measured before this change: 13 statements and 8 transactions per item (concurrency 1).
STATEMENTS_PER_ITEM_BUDGET = 10.5
TRANSACTIONS_PER_ITEM_BUDGET = 4.5


def test_an_item_costs_no_more_than_the_budget_in_statements_and_transactions(repo):
    view = _enqueue(client_ids=(1, 2, 3, 4, 5, 6, 7))
    counter = repo.statement_counter
    before = (counter.statements, counter.transactions)
    _worker(repo, _Env(), RUN_WORKER_CONCURRENCY="1").drain()
    items = view["counts"]["total"]
    assert (counter.statements - before[0]) / items <= STATEMENTS_PER_ITEM_BUDGET
    assert (counter.transactions - before[1]) / items <= TRANSACTIONS_PER_ITEM_BUDGET
    assert repo.get(view["batch_id"]).counts["items_succeeded"] == items


def test_finishing_with_a_refresh_updates_the_counters_in_the_same_transaction(repo):
    view = _enqueue(client_ids=(1, 2))
    claimed = repo.claim("w", 2, 120, NOW)
    assert [i.client_id for i in claimed] == [1, 2] and all(i.status is ItemStatus.LEASED for i in claimed)
    txns = repo.statement_counter.transactions
    assert repo.finish(claimed[0].item_id, "w", NOW, ItemResult(ItemStatus.SUCCEEDED, run_id="r"), refresh_batch=view["batch_id"])
    assert repo.statement_counter.transactions == txns + 1, "one transaction for the item and the counters"
    batch = repo.get(view["batch_id"])
    assert batch.counts["items_succeeded"] == 1 and batch.counts["items_running"] == 1 and batch.status.value == "running"


def test_refresh_returns_the_batch_exactly_as_a_read_would(repo):
    view = _enqueue(client_ids=(1, 2, 3))
    claimed = repo.claim("w", 1, 120, NOW)
    repo.finish(claimed[0].item_id, "w", NOW, ItemResult(ItemStatus.SUCCEEDED))
    refreshed = repo.refresh(view["batch_id"], NOW + timedelta(seconds=3, microseconds=123456))
    assert refreshed == repo.get(view["batch_id"])


def test_a_claim_returns_items_in_queue_order_and_never_a_client_with_a_live_lease(repo):
    _enqueue(client_ids=(1, 2, 3))
    first = repo.claim("a", 2, 120, NOW)
    assert [i.client_id for i in first] == [1, 2]
    assert [i.client_id for i in repo.claim("b", 5, 120, NOW)] == [3], "clients 1 and 2 are leased"
    assert repo.claim("c", 5, 120, NOW) == []
    later = NOW + timedelta(seconds=500)
    assert repo.reap_expired(later, 3), "the lapsed leases go back to the queue"
    assert len(repo.claim("c", 5, 120, later)) == 3, "and an expired lease no longer holds its client"


def test_lapsed_leases_are_reaped_on_the_first_tick_and_then_no_more_often_than_the_interval(repo):
    from application.runs.worker import RunWorker
    from application.runs.executor import ItemExecutor
    from config import parse_runs

    _enqueue(client_ids=(1,))
    clock = _Clock()
    settings = parse_runs({"ENVIRONMENT": "local", "RUN_WORKER_CONCURRENCY": "1", "RUN_LEASE_SECONDS": "120", "RUN_HEARTBEAT_SECONDS": "30"})
    worker = RunWorker(repo, ItemExecutor(_Env().collaborators()), settings, owner="w", clock=clock)
    calls = []
    real = repo.reap_expired
    repo.reap_expired = lambda now, attempts: calls.append(now) or real(now, attempts)
    worker.tick()
    worker.tick()
    clock.advance(10)
    worker.tick()
    assert len(calls) == 1, "once at start, then not again within the interval"
    clock.advance(30)
    worker.tick()
    assert len(calls) == 2
    worker._pool.shutdown()
