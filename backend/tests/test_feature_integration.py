"""Run batches and the program registry working together, end to end and offline. [F06.1]

A fictional program (`ZZ_DEMO_JTC`, built under a temporary rules folder by the `demo` fixture) is added by data, three
sample clients are given payroll for it, and a filtered group batch is started through the HTTP API. What these prove:
the dry run names the work without writing, the batch's manifests and Gold payloads equal single runs, a rerun after
nothing changed skips everything (when asked to), a changed rule pack reruns, a killed worker loses and duplicates
nothing, a cancel and a retry touch only what they should, and an unreachable claims store ends in a typed, visible
failure rather than a quiet empty batch. Offline fixtures only: nothing here proves behaviour on a live Warehouse.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from application.errors import DependencyUnavailable
from application.runs import selection
from application.runs.executor import ItemExecutor
from application.runs.worker import RunWorker
from config import parse_runs
from domain.runs import BatchStatus, ItemStatus
from domain.warehouse import RUN_MANIFEST_COLUMNS, RunManifest
from test_fictional_program_end_to_end import demo  # noqa: F401 - fixture

CLIENTS = (7001, 7002, 7003)
GROUP = (7001, 7002)  # the clients whose footprint is the fictional state
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
BOOK = [{"account_id": c, "name": f"Sample client {c}"} for c in CLIENTS + (7004,)]
PAGE = {"items": [{"client_id": c, "states": ["ZZ"] if c in GROUP else ["GA"], "priority_band": "settled"} for c in CLIENTS],
        "degraded": []}


class _Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Writer:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def write_run(self, payload: dict) -> dict[str, int]:
        self.payloads.append(payload)
        return {t: len(r) for t, r in payload.items() if isinstance(r, list)}

    def validate(self) -> list[dict]:
        return []


class _FlakyClaims:
    """A claims store that cannot be reached for chosen clients, and is a real one for the rest."""

    def __init__(self, real, down: set[int]) -> None:
        self._real, self.down = real, down

    def record(self, claim):
        if claim.client_id in self.down:
            raise DependencyUnavailable("claims_store", "the claims store could not be reached.", "Check the Warehouse connection.")
        return self._real.record(claim)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _calendar_scope(monkeypatch, rows) -> None:
    """What a client's scope reads, supplied for the fictional state: the sample payroll and calendar fiscal windows."""
    from datetime import date
    from types import SimpleNamespace

    from application.queries import get_scope

    scope = SimpleNamespace(total_rows=len(rows), states=["ZZ"], tax_years=sorted({r["Tax_Year"] for r in rows}),
                            pay_dates=sorted({r["Pay_Date"] for r in rows}))
    monkeypatch.setattr(get_scope, "payroll_scope", lambda account_id: scope)
    monkeypatch.setattr(get_scope, "_clients", lambda: BOOK)
    monkeypatch.setattr(get_scope, "client_fiscal_window",
                        lambda account_id, year, convention: SimpleNamespace(begin=date(year, 1, 1), end=date(year, 12, 31)))


@pytest.fixture()
def world(demo, tmp_path, monkeypatch):  # noqa: F811
    import main
    from bootstrap import run_batch_wiring, wiring
    from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository
    from infrastructure.persistence.memory_runs import InMemoryRunManifestRepository
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

    writer, claims = _Writer(), SqliteClaimRepository(tmp_path / "claims.db")
    batches, manifests = SqliteRunBatchRepository(":memory:"), InMemoryRunManifestRepository()
    original = wiring.get_claim_repository()
    wiring.set_gold_writer(writer)
    wiring.set_claim_repository(claims)
    wiring.set_override_repository(InMemoryManualOverrideRepository())
    wiring.set_run_manifest_repository(manifests)
    run_batch_wiring.set_run_batch_repository(batches)
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio_page", lambda **kw: PAGE)
    monkeypatch.setattr("application.runs.pairs._footprint", lambda: {c: (["ZZ"] if c in GROUP else ["GA"]) for c in CLIENTS})
    monkeypatch.setenv("RUN_BATCH_CONFIRM_ABOVE", "100")
    _calendar_scope(monkeypatch, demo["rows"])
    try:
        yield type("World", (), {"writer": writer, "claims": claims, "batches": batches, "manifests": manifests,
                                 "wiring": wiring, "api": TestClient(main.app), "rules": demo["rules"]})
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        wiring.set_run_manifest_repository(None)
        run_batch_wiring.set_run_batch_repository(None)
        claims.close()
        batches.close()


def _start(world, **body):
    body.setdefault("scope", {"kind": "filter", "filter": {"state": "ZZ"}})
    return world.api.post("/api/v2/run-batches", json=body)


def _worker(world, clock=None, **settings):
    s = parse_runs({"ENVIRONMENT": "local", "RUN_WORKER_CONCURRENCY": "1", **settings})
    return RunWorker(world.batches, ItemExecutor(), s, owner="e2e", clock=clock or _Clock())


def _items(world, batch_id):
    return {i.client_id: i for i in world.batches.list_items(batch_id, None, 100, 0)[0]}


def _manifest(payload: dict) -> dict:
    return dict(zip(RUN_MANIFEST_COLUMNS, payload["run_manifest_row"]))


def _record_manifests(world) -> None:
    """The recording writer stands in for the Warehouse; the manifest repository is what the skip rule reads."""
    for payload in world.writer.payloads:
        row = _manifest(payload) | {"run_status": "success", "run_completed_at": payload["run_completed_at"]}
        world.manifests.record(RunManifest(**{k: v for k, v in row.items() if k in RunManifest.__dataclass_fields__}))


def _stamp(value) -> bool:
    if isinstance(value, datetime):
        return True
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d.*", value) is not None


def _shape(payload: dict) -> dict:
    """Everything a run wrote, minus the values that are one run's own: its id and the moment it wrote."""
    own = {_manifest(payload)["run_id"], payload.get("run_completed_at")}
    out = {}
    for table, rows in payload.items():
        if isinstance(rows, list):
            out[table] = sorted(json.dumps([v for v in row if v not in own and not _stamp(v)], default=str) for row in rows
                                if isinstance(row, (list, tuple)))
    return out


# ------------------------------------------------------------------ the filtered group batch, equal to single runs


def test_a_filtered_group_batch_previews_then_equals_single_runs(world):
    preview = _start(world, dry_run=True).json()["preview"]
    assert preview["clients"] == 2 and preview["items"] == 2 and preview["programs"] == {"ZZ_DEMO_JTC": 2}
    assert world.api.get("/api/v2/run-batches").json()["total"] == 0, "a dry run creates no batch"
    assert world.writer.payloads == [], "a dry run writes nothing"

    started = _start(world, kind="assess_and_calculate", idempotency_key="group")
    assert started.status_code == 202 and started.json()["counts"]["total"] == 2
    _worker(world).drain()
    view = world.api.get(f"/api/v2/run-batches/{started.json()['batch_id']}").json()
    assert view["status"] == "succeeded" and view["counts"]["succeeded"] == 2
    items = _items(world, started.json()["batch_id"])
    assert set(items) == set(GROUP) and all(i.program_code == "ZZ_DEMO_JTC" and i.run_id for i in items.values())
    batch = {_manifest(p)["client_id"]: p for p in world.writer.payloads}
    assert set(batch) == set(GROUP)
    claims = {c: sorted((x.program_code, x.tax_year, str(x.identified_usd)) for x in world.claims.coverage(c)) for c in GROUP}

    from application.commands.run_client_calculation import RunClientCalculationCommand

    for client in GROUP:
        world.writer.payloads.clear()
        world.wiring.get_mediator().send(RunClientCalculationCommand(
            client_id=client, tax_year=items[client].tax_year, program_code="ZZ_DEMO_JTC", actor="tests"))
        single = world.writer.payloads[-1]
        assert _manifest(single)["calculation_id"] == _manifest(batch[client])["calculation_id"]
        assert _manifest(single)["program_code"] == _manifest(batch[client])["program_code"] == "ZZ_DEMO_JTC"
        assert _shape(single) == _shape(batch[client]), "the same Gold rows as a single run"
        assert claims[client] and claims[client] == sorted(
            (x.program_code, x.tax_year, str(x.identified_usd)) for x in world.claims.coverage(client))


# ------------------------------------------------------------------ skip rule and a changed rule pack


def test_a_rerun_after_nothing_changed_skips_all_and_a_changed_rule_pack_reruns_them(world):
    first = _start(world, kind="assess_and_calculate", idempotency_key="one").json()
    _worker(world).drain()
    _record_manifests(world)
    ran = len(world.writer.payloads)

    again = _start(world, kind="assess_and_calculate", skip_unchanged=True, idempotency_key="two").json()
    _worker(world).drain()
    items = _items(world, again["batch_id"])
    assert {i.status for i in items.values()} == {ItemStatus.SKIPPED_UNCHANGED}
    assert len(world.writer.payloads) == ran, "nothing was recalculated"
    assert world.batches.get(again["batch_id"]).status is BatchStatus.SUCCEEDED
    assert first["batch_id"] != again["batch_id"]

    pack = world.rules / "zz_demo_jtc" / "2025.json"
    data = json.loads(pack.read_text(encoding="utf-8"))
    data["one_zero"]["min_weekly_wages"] = 410.0
    pack.write_text(json.dumps(data), encoding="utf-8")
    changed = _start(world, kind="assess_and_calculate", skip_unchanged=True, idempotency_key="three").json()
    _worker(world).drain()
    reran = _items(world, changed["batch_id"])
    assert {i.status for i in reran.values()} == {ItemStatus.SUCCEEDED}, "a changed rule pack means the affected items rerun"
    assert len(world.writer.payloads) == ran + 2


# ------------------------------------------------------------------ worker death, cancel, retry


def test_a_killed_worker_loses_no_item_and_duplicates_none(world):
    batch = _start(world, kind="calculate", idempotency_key="kill").json()
    clock = _Clock()
    dead = _worker(world, clock, RUN_LEASE_SECONDS="30")
    claimed = world.batches.claim("dead", 1, 30, clock.now)
    assert len(claimed) == 1, "one item was leased by a worker that then died"
    clock.advance(120)
    alive = _worker(world, clock)
    alive.drain()
    items = _items(world, batch["batch_id"])
    assert {i.status for i in items.values()} == {ItemStatus.SUCCEEDED}
    assert sorted(i.attempts for i in items.values()) == [1, 2], "the orphaned item was attempted again, the other once"
    runs = [_manifest(p)["client_id"] for p in world.writer.payloads]
    assert sorted(runs) == sorted(GROUP), "each client ran exactly once: nothing lost, nothing doubled"
    dead._pool.shutdown()


def test_a_cancel_stops_what_is_queued_and_a_retry_runs_only_the_failed(world):
    cancelled = _start(world, idempotency_key="cancel").json()
    assert world.api.post(f"/api/v2/run-batches/{cancelled['batch_id']}/cancel").json()["status"] == "cancelled"
    _worker(world).drain()
    assert world.writer.payloads == [], "a cancelled batch runs nothing"

    flaky = _FlakyClaims(world.claims, {7002})
    world.wiring.set_claim_repository(flaky)
    batch = _start(world, kind="assess_and_calculate", idempotency_key="retry").json()
    clock = _Clock()
    worker = _worker(world, clock, RUN_ITEM_MAX_ATTEMPTS="1")
    worker.drain()
    items = _items(world, batch["batch_id"])
    assert items[7001].status is ItemStatus.SUCCEEDED and items[7002].status is ItemStatus.FAILED
    ran = len(world.writer.payloads)

    flaky.down.clear()
    assert world.api.post(f"/api/v2/run-batches/{batch['batch_id']}/retry-failed").json()["requeued"] == 1
    worker.drain()
    after = _items(world, batch["batch_id"])
    assert {i.status for i in after.values()} == {ItemStatus.SUCCEEDED}
    assert after[7001].attempts == 1, "the item that succeeded was not run again"
    assert [_manifest(p)["client_id"] for p in world.writer.payloads[ran:]] == [7002]


# ------------------------------------------------------------------ claims store unreachable


def test_an_unreachable_claims_store_fails_the_item_with_a_typed_cause_and_the_batch_is_partial(world):
    world.wiring.set_claim_repository(_FlakyClaims(world.claims, {7002}))
    batch = _start(world, kind="assess_and_calculate", idempotency_key="down").json()
    clock = _Clock()
    worker = _worker(world, clock, RUN_ITEM_MAX_ATTEMPTS="2")
    for _ in range(4):
        worker.drain()
        clock.advance(600)
    view = world.api.get(f"/api/v2/run-batches/{batch['batch_id']}").json()
    assert view["status"] == "partial" and view["counts"]["succeeded"] == 1 and view["counts"]["failed"] == 1
    listed = world.api.get(f"/api/v2/run-batches/{batch['batch_id']}/items", params={"status": "failed"}).json()
    failed = listed["items"][0]
    assert failed["client_id"] == 7002 and failed["error_dependency"] == "claims_store"
    assert "Check the Warehouse connection" in failed["error_message"], "the failure carries its remedy"
    assert failed["attempts"] == 2, "a transient outage was retried, then reported"


# ------------------------------------------------------------------ selecting and previewing read no payroll


def test_selecting_previewing_and_enqueueing_read_no_payroll(world, monkeypatch):
    import application.source_ports as ports

    def forbidden(*_a, **_k):
        raise AssertionError("payroll was read while selecting, previewing or enqueueing")

    monkeypatch.setattr(ports, "load_pay_periods", forbidden)
    monkeypatch.setattr(ports, "payroll_scope", forbidden)
    assert _start(world, dry_run=True).json()["preview"]["clients"] == 2
    assert _start(world, scope={"kind": "all"}, idempotency_key="all").status_code == 202
