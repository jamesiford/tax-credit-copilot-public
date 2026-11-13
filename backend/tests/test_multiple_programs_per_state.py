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
