"""Gold, manifests and the section 9 validation treat (client, program, year) as the unit. [F04c.7]

The REAL `GoldWriter` and `GoldReader` run on SQLite (`tests/data_engine_fixture.py`), over the two fictional programs of one
fictional state (`tests/two_program_world.py`). What this proves: running program B does not supersede or invalidate program
A's current rows or manifest; both are current at once; each program's reads return that program's run; and the section 9
invariants that can run on SQLite do not flag two programs for one client-year. What it cannot prove is the T-SQL behaviour of
a live Warehouse (live-checks.md).
"""
from __future__ import annotations

import pytest

from application.commands.run_client_calculation import RunClientCalculationCommand
from infrastructure.persistence.warehouse_gold import SECTION_9_QUERIES
from tests import two_program_world as world
from tests.data_engine_fixture import OfflineGoldWriter, SqliteGoldReader, SqliteWarehouse
from tests.two_program_world import ALPHA, BETA, CLIENT

#: The section 9 queries whose tables the SQLite fixture holds (the claim and finding tables live in the operational store).
_RUNNABLE = ("9.4", "9.4b", "9.4c", "9.4d", "9.4e", "9.6e", "9.6f", "9.6g", "9.6h", "9.7", "9.8")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from bootstrap import wiring
    from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    shipped_before = world.tree_digest(world.RULES)
    world.install(tmp_path, monkeypatch)
    warehouse, claims = SqliteWarehouse(), SqliteClaimRepository(tmp_path / "claims.db")
    original = wiring.get_claim_repository()
    wiring.set_gold_writer(OfflineGoldWriter(warehouse))
    wiring.set_claim_repository(claims)
    wiring.set_override_repository(InMemoryManualOverrideRepository())
    try:
        yield type("Store", (), {"warehouse": warehouse, "reader": SqliteGoldReader(warehouse), "wiring": wiring})
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        claims.close()
    assert world.tree_digest(world.RULES) == shipped_before


def _run(store, code):
    return store.wiring.get_mediator().send(RunClientCalculationCommand(client_id=CLIENT, tax_year=2025, program_code=code, actor="tests"))


def _scalar(store, sql, *values):
    return store.warehouse.connection.raw.execute(sql, values).fetchall()


def _manifests(store):
    rows = _scalar(store, "SELECT run_id, program_code, run_status, superseded_by_run_id FROM tcc_ops.run_manifest ORDER BY run_started_at")
    return [dict(zip(("run_id", "program_code", "run_status", "superseded_by"), r)) for r in rows]


def _current(store, program):
    return _scalar(store, "SELECT COUNT(*) FROM tcc_gold.unit_year_master WHERE client_id = ? AND program_code = ? AND is_current = 1",
                   CLIENT, program)[0][0]


def test_both_programs_are_current_at_once_and_neither_supersedes_the_other(store):
    _run(store, ALPHA)
    _run(store, BETA)
    manifests = _manifests(store)
    assert [m["program_code"] for m in manifests] == [ALPHA, BETA]
    assert all(m["run_status"] == "success" and m["superseded_by"] is None for m in manifests)
    assert _current(store, ALPHA) > 0 and _current(store, ALPHA) == _current(store, BETA)


def test_rerunning_one_program_supersedes_only_its_own_rows_and_manifest(store):
    _run(store, ALPHA)
    _run(store, BETA)
    beta_before = (_current(store, BETA), [m for m in _manifests(store) if m["program_code"] == BETA][0]["run_id"])
    _run(store, ALPHA)
    manifests = _manifests(store)
    alphas = [m for m in manifests if m["program_code"] == ALPHA]
    assert [m["run_status"] for m in alphas] == ["superseded", "success"] and alphas[0]["superseded_by"] == alphas[1]["run_id"]
    beta = [m for m in manifests if m["program_code"] == BETA]
    assert len(beta) == 1 and beta[0]["run_status"] == "success" and beta[0]["superseded_by"] is None
    assert (_current(store, BETA), beta[0]["run_id"]) == beta_before
    assert _current(store, ALPHA) == _current(store, BETA)


def test_each_programs_reads_return_that_programs_run_and_figures(store):
    _run(store, ALPHA)
    _run(store, BETA)
    runs = {code: store.reader.latest_run(CLIENT, code) for code in (ALPHA, BETA)}
    assert {c: r["program_code"] for c, r in runs.items()} == {ALPHA: ALPHA, BETA: BETA}
    assert store.reader.latest_run(CLIENT)["program_code"] == BETA, "with no program the latest of any answers"
    for code in (ALPHA, BETA):
        series = store.reader.headcount_series(CLIENT, tax_year=2025, method="min_max", program_code=code)
        matrix = store.reader.onezero_matrix(CLIENT, tax_year=2025, method="min_max", program_code=code)
        assert series["run"]["run_id"] == matrix["run"]["run_id"] == runs[code]["run_id"]
    years = {c: store.reader.client_year_series(CLIENT, method="min_max", program_code=c) for c in (ALPHA, BETA)}
    for code, answer in years.items():
        assert answer["run"]["program_code"] == code
    # Credit is per program: the same headcount over different statute, never summed across the two.
    credit = {c: {y["tax_year"]: y.get("annual_credit_usd") for y in answer["years"]} for c, answer in years.items()}
    assert credit[ALPHA] != credit[BETA]


def test_the_unit_grid_and_the_drill_are_filtered_to_the_program(store):
    _run(store, ALPHA)
    _run(store, BETA)
    for code in (ALPHA, BETA):
        page = store.reader.unit_page(CLIENT, method="min_max", program_code=code, limit=500)
        assert page["items"] and {i["program_code"] for i in page["items"]} == {code}
        assert page["run"]["program_code"] == code
        site = page["items"][0]["worksite_id"]
        drill = store.reader.unit_drill(CLIENT, site, tax_year=2025, method="min_max", program_code=code)
        assert drill["unit"]["program_code"] == code and drill["run"]["program_code"] == code


def test_the_section_9_invariants_do_not_flag_two_programs_for_one_client_year(store):
    _run(store, ALPHA)
    _run(store, BETA)
    _run(store, ALPHA)
    ran = 0
    for name, sql in SECTION_9_QUERIES:
        if name.split(" ")[0] in _RUNNABLE:
            ran += 1
            assert _scalar(store, sql) == [], name
    assert ran == len(_RUNNABLE)


def test_every_current_row_check_in_section_9_is_scoped_by_program():
    by_name = dict(SECTION_9_QUERIES)
    for name in ("9.1 one live claim per cell", "9.4 one current row per unit-year-method", "9.4b one current installment per window-year"):
        assert "program_code" in by_name[name].split("GROUP BY")[1], name
