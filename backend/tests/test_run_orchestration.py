"""Run orchestration: the domain rules, selection, preview, enqueue, and the worker's whole life with fake collaborators.

What this proves: state machines, the unchanged rule (including "cannot tell, so run"), that a preview writes
nothing, idempotency, limits and confirmation, retry only for transient failures, cancel between items,
crash recovery by lease expiry, and that two items of one client never run at once. What it does not prove:
behaviour on a live Warehouse (see live-checks.md) and calculation results (the end-to-end test is in
test_run_batches_end_to_end.py).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

import config
from application.commands.enqueue_run_batch import EnqueueRunBatchCommand, handle_enqueue_run_batch
from application.errors import DependencyUnavailable
from application.runs import errors, metrics, selection
from application.runs.executor import Collaborators, ItemExecutor, choose_target
from application.runs.plan import BatchRequest, preview
from application.runs.selection import Scope, resolve_clients
from application.runs.worker import RunWorker
from config_runs import parse_runs
from domain.runs import (
    BatchKind, BatchStatus, Fingerprint, IllegalTransition, ItemStatus, RunBatchItem, ScopeKind, backoff_seconds,
    batch_status, check_item_move, unchanged_decision,
)
from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

NOW = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
BOOK = [{"account_id": i, "name": f"Client {i}"} for i in range(1, 8)]
SETTINGS = parse_runs({"ENVIRONMENT": "local", "RUN_WORKER_CONCURRENCY": "3", "RUN_BATCH_CONFIRM_ABOVE": "5"})


# ------------------------------------------------------------------ domain


def test_item_moves_follow_the_state_machine():
    check_item_move(ItemStatus.QUEUED, ItemStatus.LEASED)
    check_item_move(ItemStatus.FAILED, ItemStatus.QUEUED)
    with pytest.raises(IllegalTransition):
        check_item_move(ItemStatus.SUCCEEDED, ItemStatus.QUEUED)
    with pytest.raises(IllegalTransition):
        check_item_move(ItemStatus.QUEUED, ItemStatus.SUCCEEDED)


@pytest.mark.parametrize("counts, expected", [
    ({"queued": 3}, BatchStatus.QUEUED),
    ({"queued": 1, "succeeded": 2}, BatchStatus.RUNNING),
    ({"running": 1}, BatchStatus.RUNNING),
    ({"succeeded": 2, "skipped_unchanged": 1}, BatchStatus.SUCCEEDED),
    ({"skipped_unchanged": 3}, BatchStatus.SUCCEEDED),
    ({"succeeded": 2, "failed": 1}, BatchStatus.PARTIAL),
    ({"failed": 2}, BatchStatus.FAILED),
    ({"cancelled": 2}, BatchStatus.CANCELLED),
    ({"succeeded": 1, "cancelled": 1}, BatchStatus.PARTIAL),
])
def test_batch_status_comes_from_the_item_counts(counts, expected):
    assert batch_status(counts) is expected


FULL = Fingerprint("calc", "s1", "oz", "rules/x/2025.json", "abc", 2025, "snap")


@pytest.fixture(autouse=True)
def _authored_windows(monkeypatch):
    """The fake runs have no source to resolve windows from; one authored year is enough to fingerprint."""
    monkeypatch.setattr("application.runs.fingerprint.authored_windows", lambda *a: [("2025-01-01", "2025-12-31")])


def test_unchanged_only_when_everything_known_and_equal():
    assert unchanged_decision(FULL, FULL)[0] is True


@pytest.mark.parametrize("blank", ["calculation_id", "step1_assumption_sha256", "onezero_assumption_sha256", "rule_pack_version", "source_snapshot_id"])
def test_a_missing_value_on_either_side_means_run(blank):
    from dataclasses import replace

    assert unchanged_decision(replace(FULL, **{blank: None}), FULL)[0] is False
    assert unchanged_decision(FULL, replace(FULL, **{blank: None}))[0] is False


def test_any_difference_or_no_earlier_run_means_run():
    from dataclasses import replace

    assert unchanged_decision(None, FULL)[0] is False
    assert unchanged_decision(FULL, replace(FULL, calculation_id="other"))[0] is False
    assert unchanged_decision(FULL, replace(FULL, source_snapshot_id="moved"))[0] is False
    assert unchanged_decision(FULL, replace(FULL, tax_year=2024))[0] is False


def test_code_commit_is_compared_only_when_asked():
    from dataclasses import replace

    moved = replace(FULL, code_commit="def")
    assert unchanged_decision(FULL, moved)[0] is True
    assert unchanged_decision(FULL, moved, include_code_commit=True)[0] is False


def test_backoff_is_capped_and_jittered():
    assert backoff_seconds(1, base=5, jitter=lambda: 0) == 5
    assert backoff_seconds(3, base=5, jitter=lambda: 0) == 20
    assert backoff_seconds(30, base=5, cap=120, jitter=lambda: 0) == 120
    assert backoff_seconds(1, base=5, jitter=lambda: 1) == 6.25


def test_settings_default_inline_worker_only_locally():
    assert parse_runs({"ENVIRONMENT": "local"}).worker_inline is True
    assert parse_runs({"ENVIRONMENT": "production"}).worker_inline is False
    assert parse_runs({"ENVIRONMENT": "production", "RUN_WORKER_INLINE": "true"}).worker_inline is True
    assert parse_runs({"RUN_WORKER_CONCURRENCY": "99"}).worker_concurrency == 8


# ------------------------------------------------------------------ selection


def _portfolio(**kwargs):
    rows = [
        {"client_id": 1, "priority_band": "exposed", "states": ["GA"], "status": "assessed"},
        {"client_id": 2, "priority_band": "settled", "states": ["GA", "SC"], "status": "assessed"},
        {"client_id": 3, "priority_band": "not_assessed", "states": ["TN"], "status": "not_assessed"},
        {"client_id": 99, "priority_band": "exposed", "states": [], "status": "assessed", "data_unavailable": True},
    ]
    return rows


def _resolve(scope):
    return resolve_clients(scope, book=lambda: BOOK, portfolio=_portfolio)


def test_ids_are_deduplicated_and_checked_against_the_book():
    got = _resolve(Scope(ScopeKind.LIST, (3, 1, 3)))
    assert got.client_ids == (3, 1) and got.names[3] == "Client 3"
    with pytest.raises(errors.UnknownClients):
        _resolve(Scope(ScopeKind.LIST, (1, 500)))


def test_all_is_the_whole_book_and_a_filter_narrows_the_portfolio():
    assert _resolve(Scope(ScopeKind.ALL)).client_ids == tuple(range(1, 8))
    assert _resolve(Scope(ScopeKind.FILTER, filter={"state": "sc"})).client_ids == (2,)
    assert _resolve(Scope(ScopeKind.FILTER, filter={"unassessed": True})).client_ids == (3,)
    assert _resolve(Scope(ScopeKind.FILTER, filter={"band": "exposed"})).client_ids == (1,), "99 is not in the book"


def test_an_empty_selection_and_an_unknown_filter_key_are_refused():
    with pytest.raises(errors.EmptyScope):
        _resolve(Scope(ScopeKind.FILTER, filter={"band": "declining"}))
    with pytest.raises(errors.RunBatchRefused):
        _resolve(Scope(ScopeKind.FILTER, filter={"colour": "red"}))
    with pytest.raises(errors.EmptyScope):
        _resolve(Scope(ScopeKind.LIST, ()))


# ------------------------------------------------------------------ preview and enqueue


class _Manifests:
    def __init__(self):
        self.reads = []

    def latest(self, client_id, *, program_code=None):
        self.reads.append(client_id)
        if client_id == 1:
            return None
        return type("M", (), {
            "run_id": "r", "tax_year": 2025, "run_completed_at": NOW, "calculation_id": "c", "rule_pack_version": "p",
            "step1_assumption_sha256": "s", "onezero_assumption_sha256": "o", "source_snapshot_id": "snap"})()


def _request(**kw):
    base = dict(kind=BatchKind.CALCULATE, scope=Scope(ScopeKind.LIST, (1, 2, 3)))
    base.update(kw)
    return BatchRequest(**base)


def _page(unavailable=()):
    rows = [{"client_id": i, "data_unavailable": i in unavailable, "unavailable_dependency": "claims_store" if i in unavailable else None}
            for i in range(1, 8)]
    return lambda: {"items": rows, "degraded": [{"dependency": "claims_store", "impact": "claim figures are unavailable."}] if unavailable else []}


def test_preview_states_an_upper_bound_and_writes_nothing(monkeypatch):
    m = _Manifests()
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio_page", _page())
    out = preview(_request(skip_unchanged=True), SETTINGS, manifests=lambda: m, assumptions=lambda: [{"set_id": "a", "sha256": "s"}, {"set_id": "b", "sha256": "o"}])
    assert out["clients"] == 3 and out["items"] == 3 and out["never_run"] == 1
    assert out["skip_candidates_upper_bound"] == 2
    assert any("upper bound" in n for n in out["notes"])
    assert out["first_items"][0]["last_run"]["state"] == "never_run"
    assert out["skip_coverage"] == "all_years" and out["skip_unchanged"] is True


def test_preview_names_unavailable_clients_with_the_reason_and_never_calls_them_not_assessed(monkeypatch):
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    out = preview(_request(), SETTINGS, manifests=lambda: _Manifests(), assumptions=lambda: [], portfolio_page=_page(unavailable={2}))
    assert out["unavailable_checked"] is True
    assert out["unavailable"] == [{"client_id": 2, "client_name": "Client 2", "dependency": "claims_store",
                                   "reason": "claim figures are unavailable."}]


def test_preview_says_so_when_it_cannot_find_out_which_clients_are_unavailable(monkeypatch):
    from application.errors import DependencyUnavailable

    def down():
        raise DependencyUnavailable("claims_store", "the store cannot be read.", "Run the migration.")

    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    out = preview(_request(), SETTINGS, manifests=lambda: _Manifests(), assumptions=lambda: [], portfolio_page=down)
    assert out["unavailable_checked"] is False and out["unavailable"] == []
    assert any("could not be checked" in n for n in out["notes"])


def test_preview_with_force_names_no_candidates(monkeypatch):
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio_page", _page())
    out = preview(_request(force=True), SETTINGS, manifests=lambda: _Manifests(), assumptions=lambda: [])
    assert out["skip_candidates_upper_bound"] == 0


def test_refresh_once_off_needs_explicit_years():
    with pytest.raises(errors.RunBatchRefused):
        _request(refresh_once=False).validated()
    assert _request(refresh_once=False, tax_years=(2024, 2025)).validated().tax_years == (2024, 2025)


@pytest.fixture()
def repo(monkeypatch):
    from bootstrap import run_batch_wiring as wiring

    r = SqliteRunBatchRepository(":memory:")
    wiring.set_run_batch_repository(r)
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio", _portfolio)
    monkeypatch.setattr(selection, "_portfolio_page", _page())
    monkeypatch.setattr("application.runs.plan._assumptions", lambda: [])
    monkeypatch.setattr("application.services.get_run_manifest_repository", lambda: _Manifests())
    yield r
    wiring.set_run_batch_repository(None)
    r.close()


def _enqueue(**kw):
    base = dict(actor="alice", scope_kind="list", client_ids=(1, 2, 3))
    base.update(kw)
    return handle_enqueue_run_batch(EnqueueRunBatchCommand(**base))


def test_enqueue_creates_one_item_per_client_with_no_year(repo):
    view = _enqueue()
    assert view["counts"]["total"] == 3 and view["status"] == "queued" and view["requested_by"] == "alice"
    items, _ = repo.list_items(view["batch_id"], None, 10, 0)
    assert [i.tax_year for i in items] == [None, None, None]
    assert "first_items" not in view["dry_run_summary"]


def test_explicit_years_make_one_item_per_client_year(repo):
    view = _enqueue(tax_years=(2024, 2025), client_ids=(1, 2))
    assert view["counts"]["total"] == 4


def test_the_same_request_twice_returns_the_same_batch(repo):
    a = _enqueue(idempotency_key="k")
    b = _enqueue(idempotency_key="k", client_ids=(4, 5))
    assert b["batch_id"] == a["batch_id"] and b["idempotent_replay"] is True
    c = _enqueue(client_ids=(6, 7))
    d = _enqueue(client_ids=(6, 7))
    assert d["batch_id"] == c["batch_id"] and d["idempotent_replay"] is True
    assert repo.list_batches(10, 0)[1] == 2


def test_a_large_start_needs_typed_confirmation(monkeypatch, repo):
    monkeypatch.setenv("RUN_BATCH_CONFIRM_ABOVE", "5")
    with pytest.raises(errors.ConfirmationRequired) as refused:
        _enqueue(scope_kind="all", client_ids=())
    assert refused.value.items == 7 and "confirm_items=7" in str(refused.value)
    assert repo.list_batches(10, 0)[1] == 0, "a refusal writes nothing"
    with pytest.raises(errors.ConfirmationRequired):
        _enqueue(scope_kind="all", client_ids=(), confirm_items=6)
    assert _enqueue(scope_kind="all", client_ids=(), confirm_items=7)["counts"]["total"] == 7


def test_the_size_cap_needs_an_explicit_override_and_only_for_all(monkeypatch, repo):
    monkeypatch.setenv("RUN_BATCH_MAX_ITEMS", "4")
    monkeypatch.setenv("RUN_BATCH_CONFIRM_ABOVE", "100")
    with pytest.raises(errors.BatchTooLarge):
        _enqueue(scope_kind="all", client_ids=())
    with pytest.raises(errors.BatchTooLarge):
        _enqueue(client_ids=(1, 2, 3, 4, 5))
    assert _enqueue(scope_kind="all", client_ids=(), override_size_limit=True)["counts"]["total"] == 7


def test_capability_edge_authorizes_every_client_in_a_list():
    from application.capabilities.invoke import client_ids

    assert client_ids({"client_ids": [1, 2], "arguments": {"client_ids": [3], "client_id": 4}}) == {1, 2, 3, 4}
    assert client_ids({"client_ids": [True, "5"]}) == set()


def test_commands_declare_the_writer_policy():
    from application.commands.cancel_run_batch import CancelRunBatchCommand
    from application.commands.retry_failed_items import RetryFailedItemsCommand
    from application.identity import Policy

    assert EnqueueRunBatchCommand.policy is Policy.WRITER
    assert CancelRunBatchCommand.policy is Policy.WRITER and RetryFailedItemsCommand.policy is Policy.WRITER


# ------------------------------------------------------------------ choosing the target


def _scope(**kw):
    base = {"calculable_years": [2024, 2025], "default_year": 2025, "states": ["GA"], "programs": [
        {"program_code": "GA_JTC", "jurisdiction": {"level": "state", "code": "GA"}, "authored_years": [2023, 2024, 2025]},
        {"program_code": "FED", "jurisdiction": {"level": "federal", "code": "US"}, "authored_years": [2025]},
    ]}
    base.update(kw)
    return base


def _batch_and_item(repo, **kw):
    view = _enqueue(**kw)
    batch = repo.get(view["batch_id"])
    items, _ = repo.list_items(batch.batch_id, None, 50, 0)
    return batch, items


def test_the_target_is_the_default_year_of_the_one_state_programme(repo):
    batch, items = _batch_and_item(repo)
    assert choose_target(_scope(), batch, items[0]) == ("GA", "GA_JTC", 2025)


def test_an_unsupported_year_is_a_skip_and_several_programmes_are_refused(repo):
    from application.runs.executor import Refuse, Skip

    batch, items = _batch_and_item(repo, tax_years=(2023,), client_ids=(1,))
    with pytest.raises(Skip):
        choose_target(_scope(), batch, items[0])
    two = _scope()
    two["programs"].append({"program_code": "SC_JTC", "jurisdiction": {"level": "state", "code": "SC"}, "authored_years": [2025]})
    with pytest.raises(Refuse):
        choose_target(two, batch, items[0])
    with pytest.raises(Skip):
        choose_target(_scope(calculable_years=[]), batch, items[0])


# ------------------------------------------------------------------ the worker


class _Run:
    program_code = "GA_JTC"


_ROW = {"Employee_ID": "e1", "Worksite_ID": "GA_A", "Pay_Date": "2025-03-01", "Hours_Worked": 40, "Gross_Wages": 900}


class _Env:
    """Fake collaborators: records every command and lets a test script failures per client."""

    def __init__(self):
        self.sent, self.fail, self.manifest, self.active, self.max_active = [], {}, None, {}, {}
        self.lock = threading.Lock()
        self.delay = 0.0

    def collaborators(self):
        return Collaborators(
            send=self.send, client_scope=lambda cid: _scope(), resolve_run=self.resolve_run,
            latest_manifest=lambda cid, program: self.manifest,
            assumptions=lambda: [{"set_id": "a", "sha256": "s"}, {"set_id": "b", "sha256": "o"}], code_commit=lambda: "abc")

    def resolve_run(self, *, account_id, state, tax_year):
        run = type("R", (), {})()
        run.account_id, run.program_code, run.tax_year, run.rows = account_id, "GA_JTC", tax_year, []
        run.state, run.state_rows = "GA", [_ROW]
        from datetime import date

        run.window = type("W", (), {"begin": date(2025, 1, 1), "end": date(2025, 12, 31)})()
        run.floors = type("F", (), {"as_dict": lambda self: {"source": "rules/ga_jtc/2025.json"}})()
        return run

    def send(self, command):
        cid = command.client_id
        with self.lock:
            self.active[cid] = self.active.get(cid, 0) + 1
            self.max_active[cid] = max(self.max_active.get(cid, 0), self.active[cid])
        try:
            time.sleep(self.delay)
            queue = self.fail.get(cid)
            if queue:
                raise queue.pop(0)
            self.sent.append((cid, type(command).__name__, command.tax_year if hasattr(command, "tax_year") else None))
            return {"run_id": f"run-{cid}"}
        finally:
            with self.lock:
                self.active[cid] -= 1


class _Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def _worker(repo, env, clock=None, **settings):
    s = parse_runs({"ENVIRONMENT": "local", "RUN_WORKER_CONCURRENCY": "3", "RUN_BATCH_CONFIRM_ABOVE": "100", **settings})
    return RunWorker(repo, ItemExecutor(env.collaborators()), s, owner="test", clock=clock or _Clock())


def _statuses(repo, batch_id):
    items, _ = repo.list_items(batch_id, None, 100, 0)
    return {i.client_id: i for i in items}


def test_a_batch_runs_every_item_through_the_existing_command(repo):
    env = _Env()
    view = _enqueue(client_ids=(1, 2, 3))
    _worker(repo, env).drain()
    assert sorted(env.sent) == [(1, "RunClientCalculationCommand", 2025), (2, "RunClientCalculationCommand", 2025),
                                (3, "RunClientCalculationCommand", 2025)]
    items = _statuses(repo, view["batch_id"])
    assert all(i.status is ItemStatus.SUCCEEDED and i.tax_year == 2025 and i.run_id == f"run-{i.client_id}" for i in items.values())
    assert repo.get(view["batch_id"]).status is BatchStatus.SUCCEEDED


def test_assess_batches_call_the_assess_command(repo):
    env = _Env()
    _enqueue(kind="assess", client_ids=(1,))
    _worker(repo, env).drain()
    assert env.sent == [(1, "AssessClientCommand", None)]


def test_an_unchanged_client_is_skipped_with_the_reason_and_force_overrides(repo):
    env = _Env()
    from application.runs.fingerprint import current_fingerprint

    run = env.resolve_run(account_id=1, state="GA", tax_year=2025)
    f = current_fingerprint(run, env.collaborators().assumptions(), "abc")
    env.manifest = type("M", (), {
        "calculation_id": f.calculation_id, "step1_assumption_sha256": "s", "onezero_assumption_sha256": "o",
        "rule_pack_version": f.rule_pack_version, "code_commit": "abc", "tax_year": 2025,
        "source_snapshot_id": f.source_snapshot_id})()
    view = _enqueue(client_ids=(1,), skip_unchanged=True)
    _worker(repo, env).drain()
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.SKIPPED_UNCHANGED and "identical" in item.skip_reason and env.sent == []
    assert repo.get(view["batch_id"]).status is BatchStatus.SUCCEEDED
    forced = _enqueue(client_ids=(1,), skip_unchanged=True, force=True)
    _worker(repo, env).drain()
    assert _statuses(repo, forced["batch_id"])[1].status is ItemStatus.SUCCEEDED and len(env.sent) == 1


def test_a_manifest_without_what_is_needed_to_compare_runs_the_item(repo):
    env = _Env()
    env.manifest = type("M", (), {"calculation_id": None, "step1_assumption_sha256": None, "onezero_assumption_sha256": None,
                                  "rule_pack_version": "", "code_commit": "", "tax_year": 2025})()
    _enqueue(client_ids=(1,), skip_unchanged=True)
    _worker(repo, env).drain()
    assert len(env.sent) == 1


def test_a_client_with_no_payroll_is_a_skip_not_a_failure_and_is_not_retried(repo):
    from application.queries._client_run import ClientRunNotAvailable

    env = _Env()
    env.fail[2] = [ClientRunNotAvailable("no GA payroll")]
    view = _enqueue(client_ids=(1, 2))
    _worker(repo, env).drain()
    item = _statuses(repo, view["batch_id"])[2]
    assert item.status is ItemStatus.SKIPPED_NO_PAYROLL and item.attempts == 1 and "no GA payroll" in item.skip_reason
    assert repo.get(view["batch_id"]).status is BatchStatus.SUCCEEDED


def test_a_transient_failure_is_retried_after_a_backoff_then_succeeds(repo):
    env, clock = _Env(), _Clock()
    env.fail[1] = [RuntimeError("[08001] (24556) snapshot isolation transaction aborted")]
    view = _enqueue(client_ids=(1,))
    w = _worker(repo, env, clock)
    w.drain()
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.QUEUED and item.attempts == 1 and item.error_dependency == "conflict"
    assert item.not_before > clock.now
    clock.advance(600)
    w.drain()
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.SUCCEEDED and item.attempts == 2


def test_transient_failures_stop_after_the_attempt_limit(repo):
    env, clock = _Env(), _Clock()
    env.fail[1] = [DependencyUnavailable("operational_store", "it could not be reached.", "Check it.")] * 5
    view = _enqueue(client_ids=(1,))
    w = _worker(repo, env, clock, RUN_ITEM_MAX_ATTEMPTS="2")
    for _ in range(4):
        w.drain()
        clock.advance(600)
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.FAILED and item.attempts == 2 and item.error_dependency == "operational_store"
    assert repo.get(view["batch_id"]).status is BatchStatus.FAILED


@pytest.mark.parametrize("error, dependency", [
    (ValueError("bad input"), "validation"),
    (DependencyUnavailable("lookup:pay_code_category", "unmapped", "map them"), "lookup:pay_code_category"),
])
def test_validation_and_configuration_failures_are_not_retried(repo, error, dependency):
    env = _Env()
    env.fail[1] = [error]
    view = _enqueue(client_ids=(1,))
    _worker(repo, env).drain()
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.FAILED and item.attempts == 1 and item.error_dependency == dependency


def test_a_bug_fails_the_item_once_without_echoing_the_exception(repo):
    env = _Env()
    env.fail[1] = [KeyError("hidden-host-name")]
    view = _enqueue(client_ids=(1,))
    _worker(repo, env).drain()
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.FAILED and item.error_dependency == "internal" and "hidden-host" not in item.error_message


def test_retry_failed_runs_only_the_failed_item_again(repo):
    from application.commands.retry_failed_items import RetryFailedItemsCommand, handle_retry_failed_items

    env = _Env()
    env.fail[2] = [ValueError("bad")]
    view = _enqueue(client_ids=(1, 2))
    w = _worker(repo, env)
    w.drain()
    assert repo.get(view["batch_id"]).status is BatchStatus.PARTIAL
    out = handle_retry_failed_items(RetryFailedItemsCommand(batch_id=view["batch_id"], actor="alice"))
    assert out["requeued"] == 1
    w.drain()
    assert repo.get(view["batch_id"]).status is BatchStatus.SUCCEEDED
    assert sorted(c for c, *_ in env.sent) == [1, 2], "client 1 was not run twice"


def test_cancel_stops_queued_items_but_lets_the_running_one_finish(repo):
    from application.commands.cancel_run_batch import CancelRunBatchCommand, handle_cancel_run_batch

    env = _Env()
    view = _enqueue(client_ids=(1, 2, 3, 4))
    w = _worker(repo, env, RUN_WORKER_CONCURRENCY="1")
    assert w.tick() == 1
    out = handle_cancel_run_batch(CancelRunBatchCommand(batch_id=view["batch_id"], actor="alice"))
    assert out["cancelled_now"] == 3
    w.drain()
    items = _statuses(repo, view["batch_id"])
    assert items[1].status is ItemStatus.SUCCEEDED
    assert {items[c].status for c in (2, 3, 4)} == {ItemStatus.CANCELLED}
    assert repo.get(view["batch_id"]).status is BatchStatus.PARTIAL


def test_a_crashed_worker_s_items_come_back_when_the_lease_expires(repo):
    env, clock = _Env(), _Clock()
    view = _enqueue(client_ids=(1,))
    dead = RunWorker(repo, ItemExecutor(env.collaborators()), parse_runs({"RUN_LEASE_SECONDS": "30"}), owner="dead", clock=clock)
    assert repo.claim("dead", 1, 30, clock.now)
    clock.advance(120)
    alive = _worker(repo, env, clock)
    alive.drain()
    item = _statuses(repo, view["batch_id"])[1]
    assert item.status is ItemStatus.SUCCEEDED and item.attempts == 2
    dead._pool.shutdown()


def test_two_items_of_one_client_never_run_at_the_same_time(repo):
    env = _Env()
    env.delay = 0.05
    view = _enqueue(tax_years=(2024, 2025), client_ids=(1, 2, 3))
    _worker(repo, env).drain()
    assert env.max_active and max(env.max_active.values()) == 1
    assert len(env.sent) == 6 and repo.get(view["batch_id"]).status is BatchStatus.SUCCEEDED


def test_two_workers_never_share_a_client(repo):
    env = _Env()
    env.delay = 0.03
    _enqueue(tax_years=(2024, 2025), client_ids=(1, 2))
    a, b = _worker(repo, env), _worker(repo, env)
    threads = [threading.Thread(target=w.drain) for w in (a, b)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert max(env.max_active.values()) == 1 and len(env.sent) == 4


def test_counters_record_outcomes(repo):
    metrics.reset()
    env = _Env()
    env.fail[2] = [ValueError("x")]
    _enqueue(client_ids=(1, 2))
    _worker(repo, env).drain()
    snap = metrics.snapshot()
    assert snap["items.succeeded"] == 1 and snap["items.failed"] == 1 and snap["failures.validation"] == 1


def test_a_waiting_batch_with_no_worker_reports_a_degraded_run_worker(repo):
    from application.queries.run_batch_reads import GetRunBatchQuery, handle_get_run_batch

    view = _enqueue(client_ids=(1,))
    assert handle_get_run_batch(GetRunBatchQuery(batch_id=view["batch_id"]))["degraded"] == []
    old = repo.queue_health(datetime.now(timezone.utc) + timedelta(hours=1))
    from application.queries.run_batch_reads import worker_degraded

    entry = worker_degraded(old, 300, datetime.now(timezone.utc) + timedelta(hours=1))
    assert entry and entry[0]["dependency"] == "run_worker" and "run_worker" in entry[0]["remedy"] + entry[0]["dependency"]


# ------------------------------------------------------------------ F04b.1: skipping is opt-in and covers every year


def _matching_manifest(env, **over):
    from application.runs.fingerprint import current_fingerprint

    f = current_fingerprint(env.resolve_run(account_id=1, state="GA", tax_year=2025), env.collaborators().assumptions(), "abc")
    fields = {"calculation_id": f.calculation_id, "step1_assumption_sha256": "s", "onezero_assumption_sha256": "o",
              "rule_pack_version": f.rule_pack_version, "code_commit": "abc", "tax_year": 2025,
              "source_snapshot_id": f.source_snapshot_id, **over}
    return type("M", (), fields)()


def test_the_default_batch_skips_nothing_even_when_the_last_run_matches(repo):
    env = _Env()
    env.manifest = _matching_manifest(env)
    view = _enqueue(client_ids=(1,))
    _worker(repo, env).drain()
    assert _statuses(repo, view["batch_id"])[1].status is ItemStatus.SUCCEEDED and len(env.sent) == 1
    assert repo.get(view["batch_id"]).skip_unchanged is False


def test_opting_in_skips_only_a_client_whose_client_wide_fingerprint_matches(repo):
    env = _Env()
    env.manifest = _matching_manifest(env)
    skipped = _enqueue(client_ids=(1,), skip_unchanged=True)
    _worker(repo, env).drain()
    assert _statuses(repo, skipped["batch_id"])[1].status is ItemStatus.SKIPPED_UNCHANGED and env.sent == []
    env.manifest = _matching_manifest(env, source_snapshot_id="a-prior-year-was-restated")
    reran = _enqueue(client_ids=(1,), skip_unchanged=True, idempotency_key="again")
    _worker(repo, env).drain()
    assert _statuses(repo, reran["batch_id"])[1].status is ItemStatus.SUCCEEDED and len(env.sent) == 1


def test_a_manifest_without_the_fingerprint_means_cannot_tell_so_run(repo):
    env = _Env()
    env.manifest = _matching_manifest(env, source_snapshot_id=None)
    _enqueue(client_ids=(1,), skip_unchanged=True)
    _worker(repo, env).drain()
    assert len(env.sent) == 1


def test_a_prior_year_restatement_moves_the_fingerprint_and_a_non_authored_year_does_not():
    from application.runs.fingerprint import client_data_fingerprint

    prior = {**_ROW, "Pay_Date": "2024-06-01"}
    unauthored = {**_ROW, "Pay_Date": "2010-06-01"}
    windows = [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")]
    base = client_data_fingerprint([_ROW, prior, unauthored], windows)
    assert base == client_data_fingerprint([unauthored, prior, _ROW], windows), "independent of row order"
    assert base != client_data_fingerprint([_ROW, {**prior, "Gross_Wages": 901}, unauthored], windows), "prior year restated"
    assert base == client_data_fingerprint([_ROW, prior, {**unauthored, "Gross_Wages": 1}], windows), "unauthored year ignored"
    assert client_data_fingerprint([_ROW], []) is None, "nothing authored: cannot tell"


def test_the_default_preview_names_no_skip_candidates_and_says_nothing_is_skipped(monkeypatch):
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio_page", _page())
    old = type("M", (), {"run_id": "r", "tax_year": 2025, "run_completed_at": NOW, "calculation_id": "c", "rule_pack_version": "p",
                         "step1_assumption_sha256": "s", "onezero_assumption_sha256": "o"})()
    out = preview(_request(), SETTINGS, manifests=lambda: type("R", (), {"latest": lambda self, c, program_code=None: old})(),
                  assumptions=lambda: [{"set_id": "a", "sha256": "s"}])
    assert out["skip_unchanged"] is False and out["skip_candidates_upper_bound"] == 0
    assert out["skip_coverage"] == "cannot_tell_yet" and "Nothing is skipped" in out["notes"][0]
