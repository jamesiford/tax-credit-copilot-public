"""Measure the run batch queue at scale on synthetic accounts, with no engine and no live store. [F06.2]

    python scripts/run-batch-scale-check.py [--accounts 3000] [--item-ms 5] [--concurrency 1 2 4]

What it measures: start-to-finish orchestration of one batch (resolve the book, dry run, enqueue, lease, run, finish,
count) over an in-memory SQLite queue, with a stand-in for the run command that sleeps `--item-ms` per item. So the
numbers are the QUEUE'S cost and how `RUN_WORKER_CONCURRENCY` scales when an item is dominated by waiting; they are not
engine or Warehouse figures and must not be read as production throughput. It also proves that resolving a selection and
the dry run read no payroll (the payroll reads are replaced by functions that fail the run if called).
"""
from __future__ import annotations

import argparse
import sys
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

PROGRAM = "GA_JTC"


class _PayrollTouched(AssertionError):
    pass


class _Guard:
    """Fails the run if payroll is read while `armed`; the item stand-in runs with it off."""
    armed = False


def _forbid_payroll() -> None:
    import application.source_ports as ports

    def forbid(real):
        def guarded(*args, **kwargs):
            if _Guard.armed:
                raise _PayrollTouched("payroll was read while selecting or previewing a batch")
            return real(*args, **kwargs)
        return guarded

    for name in ("load_pay_periods", "payroll_scope"):
        setattr(ports, name, forbid(getattr(ports, name)))


def _book(accounts: int) -> list[dict]:
    from data.source.scale import FIRST_ACCOUNT_ID

    return [{"account_id": FIRST_ACCOUNT_ID + i, "name": f"Scale Account {i + 1:05d}"} for i in range(accounts)]


def _install(book: list[dict], item_ms: float):
    """Wire an in-memory queue and a fake run command; return the repository and the executor."""
    from application.runs import selection
    from application.runs.executor import Collaborators, ItemExecutor
    from bootstrap import run_batch_wiring
    from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

    repo = SqliteRunBatchRepository(":memory:")
    run_batch_wiring.set_run_batch_repository(repo)
    selection._book = lambda: book
    selection._portfolio_page = lambda **kw: {"items": [], "degraded": []}
    import application.runs.pairs as pairs

    pairs._footprint = lambda: {b["account_id"]: ["GA"] for b in book}
    scope = {"programs": [{"program_code": PROGRAM, "jurisdiction": {"level": "state", "code": "GA"}, "authored_years": [2025]}],
             "calculable_years": [2025], "default_year": 2025}

    def send(command):
        time.sleep(item_ms / 1000)
        return {"run_id": "r"}

    return repo, ItemExecutor(Collaborators(
        send=send, client_scope=lambda c: scope, resolve_run=lambda **kw: SimpleNamespace(program_code=PROGRAM),
        latest_manifest=lambda c, p: None))


def _run_once(accounts: int, item_ms: float, concurrency: int) -> dict:
    from application.commands.enqueue_run_batch import EnqueueRunBatchCommand, handle_enqueue_run_batch
    from application.queries.run_batch_reads import PreviewRunBatchQuery
    from application.runs.worker import RunWorker
    from bootstrap.wiring import get_mediator
    from config import parse_runs

    book = _book(accounts)
    repo, executor = _install(book, item_ms)
    ids = tuple(b["account_id"] for b in book)
    started = time.perf_counter()
    base = dict(actor="scale-check", scope_kind="list", client_ids=ids, kind="calculate", confirm_items=accounts)
    _Guard.armed = True
    try:
        get_mediator().send(PreviewRunBatchQuery(kind="calculate", scope_kind="list", client_ids=ids))
        preview_s = time.perf_counter() - started
        view = handle_enqueue_run_batch(EnqueueRunBatchCommand(**base))
    finally:
        _Guard.armed = False
    enqueued_s = time.perf_counter() - started
    settings = parse_runs({"ENVIRONMENT": "local", "RUN_WORKER_CONCURRENCY": str(concurrency), "RUN_BATCH_CONFIRM_ABOVE": str(accounts * 2)})
    worker = RunWorker(repo, executor, settings, owner="scale")
    before = (repo.statement_counter.statements, repo.statement_counter.transactions)
    worker.drain()
    total_s = time.perf_counter() - started
    spent = (repo.statement_counter.statements - before[0], repo.statement_counter.transactions - before[1])
    done = repo.get(view["batch_id"])
    worker._pool.shutdown()
    repo.close()
    return {"concurrency": concurrency, "items": accounts, "status": done.status.value, "preview_s": round(preview_s, 2),
            "enqueue_s": round(enqueued_s - preview_s, 2), "total_s": round(total_s, 2),
            "items_per_s": round(accounts / max(total_s - enqueued_s, 1e-9), 1),
            "statements_per_item": round(spent[0] / accounts, 2), "transactions_per_item": round(spent[1] / accounts, 2)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--accounts", type=int, default=3000)
    parser.add_argument("--item-ms", type=float, default=5.0, help="simulated wait inside each item")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4])
    args = parser.parse_args(argv)
    _forbid_payroll()
    print(f"accounts={args.accounts} simulated item wait={args.item_ms} ms (no engine, no Warehouse)")
    for level in args.concurrency:
        print(_run_once(args.accounts, args.item_ms, level))
    tracemalloc.start()
    _run_once(args.accounts, args.item_ms, 1)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"python heap peak during a {args.accounts}-item batch (tracemalloc, concurrency 1): {peak / 1_048_576:.1f} MiB")
    print("payroll reads while selecting and previewing: 0 (any read would have failed the run)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
