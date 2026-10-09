"""WI-21: "pull down a drop down and say, this is going to be a base year."

A rebase re-prices the run's own averages through the function the write path
used. So the anchor test is equivalence: rebasing to the base the run itself
inferred must reproduce the run's credit to the dollar. Everything else — years
before the base dropping out, YR1..YRn, DNQ — follows from the same engine.
"""
from __future__ import annotations

import copy
from contextlib import nullcontext
from datetime import date

import pytest

from application.queries import rebase_unit as ru
from application.queries.simulate_unit import _unit_reading
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from data.source.to_bcs import source_to_bcs_rows
from domain.calculation.onezero import run_min_max_method
from tools.credit_math import load_pack_one_zero
from tools.unit_trend import unit_status, unit_trend

SITE = "GA_GA-010"


@pytest.fixture(scope="module")
def gold():
    """GA-010's Gold rows as the write path would have written them."""
    rows = [r for r in source_to_bcs_rows(build_synthetic_dataset(SYNTHETIC_CLIENTS[0])) if r["Work_State"] == "GA"]
    averages = {}
    for year in range(2020, 2026):
        year_rows = [r for r in rows if r["Pay_Date"][:4] == str(year)]
        result = run_min_max_method(
            year_rows, tax_year=year, analysis_start_month=date(year, 1, 1),
            pack=load_pack_one_zero("GA", tax_year=year), fiscal_window=(date(year, 1, 1), date(year, 12, 31)),
        )
        averages[year] = _unit_reading(result, SITE)
    trend = unit_trend(
        {y: {"average_headcount": a["average_headcount"]} for y, a in averages.items()},
        state="GA", base_year=2020, threshold=2.0, per_job_usd=3500.0, tranche_years=5,
    )
    stairs = {s.year: s for s in trend.years}
    out = []
    for year, reading in averages.items():
        stair = stairs.get(year)
        out.append({
            "worksite_id": SITE, "tax_year": year, "is_base_year": year == 2020,
            "average_headcount": reading["average_headcount"],
            "months_with_headcount": reading["months_with_headcount"], "months_reachable": 11,
            "threshold": 2.0 if stair else None, "per_job_usd": 3500.0, "tranche_years": 5,
            "qualified": bool(stair and stair.qualified),
            "annual_credit_usd": stair.annual_credit_usd if stair else 0.0,
            "status": unit_status(
                tax_year=year, base_year=2020, qualified=bool(stair and stair.qualified),
                months_with_headcount=reading["months_with_headcount"], months_reachable=11,
            ),
        })
    return out


class _Reader:
    def __init__(self, rows):
        self.rows = rows

    def scope(self):
        return nullcontext()

    def latest_run(self, client_id):
        return {"run_id": "r1"}

    def unit_years(self, client_id, *, method, limit):
        return self.rows, len(self.rows)


@pytest.fixture
def wired(monkeypatch, gold):
    import application.wiring as wiring

    rows = copy.deepcopy(gold)
    monkeypatch.setattr(wiring, "get_gold_reader", lambda: _Reader(rows))
    return rows


def _rebase(base_year, **kw):
    return ru.handle_rebase_unit(ru.RebaseUnitQuery(client_id=2001, worksite_id=SITE, base_year=base_year, **kw))


def test_rebasing_to_the_inferred_base_reproduces_the_run(wired):
    answer = _rebase(2020)
    assert answer["inferred_base_year"] == 2020
    assert answer["total_annual_credit_usd"] == answer["run_total_annual_credit_usd"]
    assert answer["delta_annual_credit_usd"] == 0
    by_year = {y["tax_year"]: y for y in answer["years"]}
    for row in wired:
        if row["tax_year"] > 2020:
            assert by_year[row["tax_year"]]["annual_credit_usd"] == round(row["annual_credit_usd"])
            assert by_year[row["tax_year"]]["status"] == row["status"]


def test_a_later_base_greys_the_years_before_it_and_counts_years_from_it(wired):
    answer = _rebase(2022)
    roles = {y["tax_year"]: y["role"] for y in answer["years"]}
    assert roles == {2020: "before_base", 2021: "before_base", 2022: "base",
                     2023: "evaluated", 2024: "evaluated", 2025: "evaluated"}
    evaluated = [y for y in answer["years"] if y["role"] == "evaluated"]
    assert [y["year_number"] for y in evaluated] == [1, 2, 3]
    base_avg = next(r["average_headcount"] for r in wired if r["tax_year"] == 2022)
    for y in evaluated:
        assert y["net_new_vs_base"] == pytest.approx(max(0.0, y["average_headcount"] - base_avg), abs=0.011)


def test_a_higher_base_is_worth_less_and_says_by_how_much(wired):
    """GA-010 grew every year, so measuring from later is measuring from higher."""
    answer = _rebase(2023)
    assert answer["total_annual_credit_usd"] < answer["run_total_annual_credit_usd"]
    assert answer["delta_annual_credit_usd"] == answer["total_annual_credit_usd"] - answer["run_total_annual_credit_usd"]
    assert answer["saved"] is False
    assert "Not saved" in answer["note"]


def test_a_year_short_of_the_minimum_is_dnq(wired):
    """A base close to a later year leaves too little net-new to clear two jobs."""
    answer = _rebase(2024)
    ty2025 = next(y for y in answer["years"] if y["tax_year"] == 2025)
    if ty2025["net_new_vs_base"] < 2.0:
        assert ty2025["status"] == "below_minimum"
        assert ty2025["annual_credit_usd"] == 0


def test_a_partial_year_cannot_be_a_base(wired):
    for row in wired:
        if row["tax_year"] == 2021:
            row["months_with_headcount"] = 5
    with pytest.raises(ru.RebaseNotAvailable, match="partial"):
        _rebase(2021)
    assert 2021 not in _rebase(2020)["candidate_base_years"]


def test_unknown_location_and_year_are_declined(wired):
    with pytest.raises(ru.RebaseNotAvailable, match="no calculated run"):
        ru.handle_rebase_unit(ru.RebaseUnitQuery(client_id=2001, worksite_id="GA_NOPE", base_year=2022))
    with pytest.raises(ru.RebaseNotAvailable, match="no TY2019"):
        _rebase(2019)


def test_an_open_year_is_read_never_priced_and_never_a_base(wired):
    """TY2026 is still running. It must not enter the priced series — the
    closed years reprice to the dollar with it present — it cannot be a base,
    and it reads against the base as on-track, with no credit."""
    base_avg = next(r["average_headcount"] for r in wired if r["tax_year"] == 2020)
    wired.append({
        "worksite_id": SITE, "tax_year": 2026, "is_base_year": False,
        "average_headcount": base_avg + 50.0, "months_with_headcount": 8, "months_reachable": 8,
        "threshold": 2.0, "per_job_usd": 3500.0, "tranche_years": 5,
        "qualified": True, "annual_credit_usd": 0.0, "status": "in_progress",
    })
    answer = _rebase(2020)
    assert 2026 not in answer["candidate_base_years"]
    assert answer["delta_annual_credit_usd"] == 0
    ty2026 = next(y for y in answer["years"] if y["tax_year"] == 2026)
    assert ty2026["status"] == "in_progress"
    assert ty2026["annual_credit_usd"] == 0
    assert ty2026["net_new_vs_base"] == pytest.approx(50.0, abs=0.011)
    with pytest.raises(ru.RebaseNotAvailable, match="still open"):
        _rebase(2026)
