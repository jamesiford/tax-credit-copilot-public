"""Two programs in one state: the program, not the state, is the key. [F04c]

A temporary rules folder registers `ZZ_ALPHA_JTC` and `ZZ_BETA_JTC` in the made-up state ZZ beside the shipped Georgia program
(see `tests/two_program_world.py`). What this proves is offline: resolution, pricing, the run command, the claims and the batch
planner treat `(client, program, year)` as the unit. What it cannot prove is the behaviour of a live Warehouse (live-checks.md).
"""
from __future__ import annotations

import logging

import pytest

from application.queries._client_run import (
    ClientRunNotAvailable, ProgramStateConflict, resolve_client_run, resolve_statute,
)
from tests import two_program_world as world
from tests.two_program_world import ALPHA, BETA, CLIENT, STATE


@pytest.fixture()
def zz(tmp_path, monkeypatch):
    shipped_before = world.tree_digest(world.RULES)
    yield world.install(tmp_path, monkeypatch)
    assert world.tree_digest(world.RULES) == shipped_before, "the shipped rules folder must not change"


def test_an_explicit_program_wins_and_each_program_resolves_its_own_statute(zz):
    alpha = resolve_statute(account_id=CLIENT, program_code=ALPHA, tax_year=2025)
    beta = resolve_statute(account_id=CLIENT, program_code=BETA.lower(), tax_year=2025)
    assert (alpha.program_code, alpha.state, beta.program_code, beta.state) == (ALPHA, STATE, BETA, STATE)
    assert alpha.floors.program_code == ALPHA and beta.floors.program_code == BETA
    assert alpha.pack.citation == beta.pack.citation  # same fictional citation text, different packs below
    assert alpha.floors.pack_file != beta.floors.pack_file


def test_a_state_alone_uses_the_first_program_and_warns_naming_every_candidate(zz, caplog):
    with caplog.at_level(logging.WARNING):
        resolved = resolve_statute(account_id=CLIENT, state=STATE, tax_year=2025)
    assert resolved.program_code == ALPHA
    assert any(ALPHA in r.message and BETA in r.message for r in caplog.records)


def test_naming_neither_derives_the_state_from_payroll_then_applies_the_same_fallback(zz):
    assert resolve_statute(account_id=CLIENT, tax_year=2025).program_code == ALPHA


def test_a_state_with_one_authored_program_for_the_year_does_not_warn(tmp_path, monkeypatch, caplog):
    world.install(tmp_path, monkeypatch, second_authored=False)
    with caplog.at_level(logging.WARNING):
        resolved = resolve_statute(account_id=CLIENT, state=STATE, tax_year=2025)
    assert resolved.program_code == ALPHA and not caplog.records


def test_a_state_and_a_program_that_disagree_are_refused_with_a_typed_error(zz):
    with pytest.raises(ProgramStateConflict, match="not GA"):
        resolve_statute(account_id=CLIENT, state="GA", program_code=ALPHA, tax_year=2025)
    from application.commands.run_client_calculation import RunClientCalculationCommand

    with pytest.raises(ValueError, match="not GA"):  # a 422 at the route: the command refuses at construction
        RunClientCalculationCommand(client_id=CLIENT, tax_year=2025, state="GA", program_code=BETA)


def test_a_federal_or_unknown_program_declines_by_name(zz):
    with pytest.raises(ClientRunNotAvailable, match="federal programs are described but not runnable"):
        resolve_statute(account_id=CLIENT, program_code="FED_WOTC", tax_year=2025)
    with pytest.raises(ClientRunNotAvailable, match="no active program"):
        resolve_statute(account_id=CLIENT, program_code="NOPE", tax_year=2025)


def test_two_programs_in_one_state_see_the_same_rows_and_differ_only_by_pack(zz):
    a = resolve_client_run(account_id=CLIENT, program_code=ALPHA, tax_year=2025)
    b = resolve_client_run(account_id=CLIENT, program_code=BETA, tax_year=2025)
    assert a.rows == b.rows and a.rows and a.window == b.window
    assert a.pack is not b.pack and a.program_code != b.program_code


def test_a_georgia_program_resolves_exactly_as_before(zz):
    by_state = resolve_statute(account_id=None, state="GA", tax_year=2024)
    by_code = resolve_statute(account_id=None, program_code="GA_JTC", tax_year=2024)
    assert by_state.program_code == by_code.program_code == "GA_JTC"
    assert by_state.floors == by_code.floors and by_state.pack == by_code.pack


# ------------------------------------------------------------------ running both programs for one client


class _Writer:
    """Records what each run hands the Gold writer; the real writer's per-program supersession is T-SQL (live-checks.md)."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def write_run(self, payload: dict) -> dict[str, int]:
        self.payloads.append(payload)
        return {t: len(r) for t, r in payload.items() if isinstance(r, list)}

    def validate(self) -> list[dict]:
        return []


@pytest.fixture()
def runs(zz, tmp_path):
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
    try:
        yield type("Runs", (), {"writer": writer, "claims": claims, "batches": batches, "manifests": manifests, "wiring": wiring})
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        wiring.set_run_manifest_repository(None)
        run_batch_wiring.set_run_batch_repository(None)
        claims.close()
        batches.close()


def _run(runs, **kw):
    from application.commands.run_client_calculation import RunClientCalculationCommand

    return runs.wiring.get_mediator().send(RunClientCalculationCommand(client_id=CLIENT, tax_year=2025, actor="tests", **kw))


def _manifest(payload: dict) -> dict:
    from domain.warehouse import RUN_MANIFEST_COLUMNS

    return dict(zip(RUN_MANIFEST_COLUMNS, payload["run_manifest_row"]))


def _cells(runs):
    return {(c.program_code, c.tax_year): c for c in runs.claims.coverage(CLIENT)}


def test_each_program_runs_by_code_with_its_own_rows_and_manifest(runs):
    first = _run(runs, program_code=ALPHA)
    second = _run(runs, program_code=BETA)
    assert (first["program_code"], second["program_code"]) == (ALPHA, BETA) and first["state"] == second["state"] == STATE
    alpha, beta = (_manifest(p) for p in runs.writer.payloads)
    assert (alpha["program_code"], beta["program_code"]) == (ALPHA, BETA) and alpha["run_id"] != beta["run_id"]
    assert alpha["rule_pack_version"] != beta["rule_pack_version"] or alpha["calculation_id"] != beta["calculation_id"]
    from tools import gold_projection as gp

    for payload, code in zip(runs.writer.payloads, (ALPHA, BETA)):
        masters = [dict(zip(gp.UNIT_YEAR_MASTER_COLUMNS, r)) for r in payload["unit_year_master"]]
        assert masters and {m["program_code"] for m in masters} == {code}
        assert {m["per_job_usd"] for m in masters if m.get("per_job_usd")} <= {float(world.STATUTE[code][0])}


def test_the_planner_makes_one_item_per_program_for_a_client_with_two_in_one_state(zz):
    from application.runs.pairs import client_pairs

    assert client_pairs((CLIENT,), None, footprint=lambda: {CLIENT: [STATE]}) == [(CLIENT, ALPHA), (CLIENT, BETA)]
    assert client_pairs((CLIENT,), BETA, footprint=lambda: {CLIENT: [STATE]}) == [(CLIENT, BETA)]


def test_a_batch_runs_each_program_item_under_its_own_program(runs, monkeypatch):
    from application.commands.enqueue_run_batch import EnqueueRunBatchCommand, handle_enqueue_run_batch
    from application.runs.executor import ItemExecutor
    from application.runs.worker import RunWorker
    from config import get_settings
    import application.source_ports as source_ports
    from application.queries import get_scope
    from application.runs import selection
    from domain.runs import ItemStatus

    book = [{"account_id": CLIENT, "name": "Zedland client"}]
    monkeypatch.setattr(selection, "_book", lambda: book)
    monkeypatch.setattr(get_scope, "_clients", lambda: book)
    monkeypatch.setattr(get_scope, "payroll_scope", source_ports.payroll_scope)
    monkeypatch.setattr("application.runs.pairs._footprint", lambda: {CLIENT: [STATE]})
    view = handle_enqueue_run_batch(EnqueueRunBatchCommand(
        actor="tests", scope_kind="list", client_ids=(CLIENT,), kind="calculate", tax_years=(2025,),
    ))
    RunWorker(runs.batches, ItemExecutor(), get_settings().runs, owner="f04c").drain()
    items = runs.batches.list_items(view["batch_id"], None, 10, 0)[0]
    assert sorted((i.program_code, i.status) for i in items) == [(ALPHA, ItemStatus.SUCCEEDED), (BETA, ItemStatus.SUCCEEDED)]
    assert sorted(_manifest(p)["program_code"] for p in runs.writer.payloads) == [ALPHA, BETA]


def test_a_base_year_names_its_program_and_refuses_a_state_that_disagrees(zz):
    from application.commands.set_base_year import BaseYearNotAllowed, SetBaseYearCommand, resolved

    done = resolved(SetBaseYearCommand(client_id=CLIENT, worksite_id="ZZ_001", base_year=2024, program_code=BETA.lower()))
    assert (done.state, done.program_code) == (STATE, BETA)
    with pytest.raises(ValueError, match="not GA"):
        SetBaseYearCommand(client_id=CLIENT, worksite_id="ZZ_001", base_year=2024, state="GA", program_code=BETA)
    with pytest.raises(BaseYearNotAllowed, match="no active program"):
        resolved(SetBaseYearCommand(client_id=CLIENT, worksite_id="ZZ_001", base_year=2024, program_code="NOPE"))


def test_the_base_year_capability_carries_an_optional_program_to_its_command(zz):
    from application.capabilities.write_specs import SPECS
    from types import SimpleNamespace

    principal = SimpleNamespace(actor="tests")  # `build` reads only the actor
    command = SPECS["base_year_set"].build(principal, {"client_id": CLIENT, "unit_id": "ZZ_001", "base_year": 2024, "program_code": BETA})
    assert command.program_code == BETA
