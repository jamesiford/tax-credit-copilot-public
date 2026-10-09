"""A location's what-if must agree with the location grid that opened it.

The client-wide simulator measures against the PRIOR year; the grid measures a
location against its OWN frozen base. At Cascade GA-016 in TY2025 those are
13.67 and 7.33, so pricing a location projection the client-wide way would
tell the reader that hiring two people does nothing while the grid says it
clears the minimum. These tests fake Gold from the same engine and the same
`unit_trend` the write path uses, then hold the simulator to it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from application.queries import simulate_unit as su
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from data.source.to_bcs import source_to_bcs_rows
from domain.calculation.onezero import run_min_max_method
from tools.credit_math import load_pack_one_zero
from tools.unit_trend import unit_status, unit_trend

CASCADE = SYNTHETIC_CLIENTS[0]
# GA-007 carries the TY2025 below-minimum story against a TY2020 base. GA-016
# did until 30 Sep, when it became a store that opens with TY2023.
SITE = "GA_GA-007"
YEARS = range(2020, 2026)


@dataclass
class _Run:
    rows: list[dict[str, Any]]
    tax_year: int
    program_code: str = "GA_JTC"

    def engine_kwargs(self) -> dict[str, Any]:
        begin, end = date(self.tax_year, 1, 1), date(self.tax_year, 12, 31)
        return {
            "tax_year": self.tax_year, "analysis_start_month": begin,
            "pack": load_pack_one_zero("GA", tax_year=self.tax_year),
            "fiscal_window": (begin, end),
        }


@pytest.fixture(scope="module")
def cascade():
    rows = [r for r in source_to_bcs_rows(build_synthetic_dataset(CASCADE)) if r["Work_State"] == "GA"]
    by_year = {y: [r for r in rows if r["Pay_Date"][:4] == str(y)] for y in YEARS}
    averages: dict[int, dict[str, Any]] = {}
    for year, year_rows in by_year.items():
        reading = su._unit_reading(run_min_max_method(year_rows, **_Run(year_rows, year).engine_kwargs()), SITE)
        averages[year] = reading
    pack = load_pack_one_zero("GA", tax_year=2025)
    trend = unit_trend(
        {y: {"average_headcount": a["average_headcount"]} for y, a in averages.items()},
        state="GA", base_year=2020, threshold=2.0, per_job_usd=3500.0, tranche_years=5,
    )
    stairs = {y.year: y for y in trend.years}
    gold = []
    for year, reading in averages.items():
        stair = stairs.get(year)
        gold.append({
            "worksite_id": SITE, "tax_year": year, "is_base_year": year == 2020,
            "average_headcount": reading["average_headcount"],
            "months_with_headcount": reading["months_with_headcount"], "months_reachable": 12,
            "threshold": 2.0 if stair else None, "per_job_usd": 3500.0, "tranche_years": 5,
            "qualified": bool(stair.qualified) if stair else False,
            "annual_credit_usd": stair.annual_credit_usd if stair else 0.0,
            "status": unit_status(
                tax_year=year, base_year=2020, qualified=bool(stair and stair.qualified),
                months_with_headcount=reading["months_with_headcount"],
            ),
        })
    assert pack is not None
    return by_year, gold


class _Reader:
    def __init__(self, gold):
        self.gold = gold

    def scope(self):
        from contextlib import nullcontext
        return nullcontext()

    def latest_run(self, client_id):
        return {"run_id": "test-run"}

    def unit_years(self, client_id, *, method, limit):
        return self.gold, len(self.gold)


@pytest.fixture
def wired(monkeypatch, cascade):
    import copy

    by_year, shared = cascade
    gold = copy.deepcopy(shared)
    import application.queries._client_run as client_run
    import application.wiring as wiring

    monkeypatch.setattr(wiring, "get_gold_reader", lambda: _Reader(gold))
    monkeypatch.setattr(
        client_run, "resolve_client_run",
        lambda *, account_id, state, tax_year, rows=None: _Run(by_year[tax_year], tax_year),
    )
    return gold


def _ask(**overrides):
    params = dict(client_id=2001, worksite_id=SITE, tax_year=2025, action="add_headcount", magnitude=2)
    params.update(overrides)
    return su.handle_simulate_unit(su.SimulateUnitQuery(**params))


def test_the_baseline_is_the_grid_row(wired):
    grid = next(row for row in wired if row["tax_year"] == 2025)
    answer = _ask()
    assert answer["baseline"]["average_headcount"] == pytest.approx(grid["average_headcount"], abs=0.011)
    assert answer["baseline"]["status"] == grid["status"] == "below_minimum"
    assert answer["baseline"]["annual_credit_usd"] == 0
    assert answer["base_year"] == 2020


def test_two_hires_clear_the_minimum_the_grid_measures(wired):
    """Against its own TY2020 base, not the prior year: that is what the grid shows."""
    answer = _ask(magnitude=2)
    assert answer["projected"]["status"] == "above_minimum"
    assert answer["projected"]["jobs_margin"] >= 0
    assert answer["projected"]["annual_credit_usd"] == round(answer["projected"]["eligible_jobs"] * 3500)
    assert SITE in answer["detail"]


def test_one_hire_is_not_enough_and_says_so(wired):
    answer = _ask(magnitude=1)
    assert answer["projected"]["status"] == "below_minimum"
    assert answer["projected"]["jobs_margin"] < 0
    assert answer["delta"]["annual_credit_usd"] == 0


def test_a_base_year_is_not_a_what_if(wired):
    with pytest.raises(su.UnitSimulationNotAvailable, match="base year"):
        _ask(tax_year=2020)


def test_drifted_payroll_is_declined_rather_than_projected(wired):
    for row in wired:
        if row["tax_year"] == 2025:
            row["average_headcount"] += 3
    with pytest.raises(su.UnitSimulationNotAvailable, match="no longer reproduces"):
        _ask()


def test_an_unknown_location_is_declined(wired):
    with pytest.raises(su.UnitSimulationNotAvailable, match="no calculated run holds"):
        _ask(worksite_id="GA_NOPE")


def test_the_query_refuses_an_unknown_lever():
    with pytest.raises(ValueError):
        su.SimulateUnitQuery(client_id=1, worksite_id="x", tax_year=2025, action="bribe")


# ------------------------------------------------ WI-22: hire with hours and pay


def test_a_hire_that_clears_both_floors_counts(wired):
    answer = _ask(magnitude=2, hire_weekly_hours=40, hire_hourly_rate=25)
    assert answer["projected"]["status"] == "above_minimum"
    assert "clear of both floors" in answer["detail"]


def test_a_part_time_hire_moves_nothing_and_says_why(wired):
    answer = _ask(magnitude=2, hire_weekly_hours=30, hire_hourly_rate=25)
    assert answer["delta"]["average_headcount"] == 0
    assert answer["projected"]["status"] == "below_minimum"
    assert "35-hour floor" in answer["detail"]


def test_an_underpaid_hire_moves_nothing_and_says_why(wired):
    """40 hrs at $15 is $600 a week, under Georgia's $680 for TY2025."""
    answer = _ask(magnitude=2, hire_weekly_hours=40, hire_hourly_rate=15)
    assert answer["delta"]["average_headcount"] == 0
    assert "wage floor" in answer["detail"]


def test_without_hours_or_pay_a_hire_is_the_full_time_role_it_always_was(wired):
    assert _ask(magnitude=2)["projected"] == _ask(magnitude=2, hire_weekly_hours=None, hire_hourly_rate=None)["projected"]
    assert "full-time heads" in _ask(magnitude=2)["detail"]


@pytest.mark.parametrize("hours,rate", [(0, 20), (81, 20), (40, 0), (40, 501)])
def test_an_impossible_role_is_refused(hours, rate):
    with pytest.raises(ValueError):
        su.SimulateUnitQuery(client_id=1, worksite_id="x", tax_year=2025,
                             hire_weekly_hours=hours, hire_hourly_rate=rate)


def test_each_new_head_works_the_stated_week_in_every_period():
    from datetime import date as _d

    from tools.credit_math import load_pack_one_zero
    from tools.simulation import apply_onezero_lever

    rows = [{"Employee_ID": "E1", "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-14",
             "Hours_Worked": 80.0, "Gross_Wages": 2000.0, "Worksite_ID": "GA_GA-016"}]
    moved, _ = apply_onezero_lever(rows, action="add_headcount", magnitude=1,
                                   pack=load_pack_one_zero("GA", tax_year=2025), state="GA",
                                   hire_weekly_hours=30, hire_hourly_rate=20)
    new = [r for r in moved if r["Employee_ID"].startswith("SIM_")]
    assert new[0]["Hours_Worked"] == pytest.approx(60.0)   # two weeks at 30
    assert new[0]["Gross_Wages"] == pytest.approx(1200.0)  # at $20/hr


def test_the_margin_is_measured_from_the_base_not_from_clamped_net_new():
    """Net new clamps at zero, so a location BELOW its base read "2.00 short"
    however far below it sat. The margin a reader is shown is the real gap."""
    from types import SimpleNamespace

    below = SimpleNamespace(average_headcount=3.0, base_average_headcount=7.33, net_new=0.0, threshold=2.0)
    above = SimpleNamespace(average_headcount=9.67, base_average_headcount=7.33, net_new=2.34, threshold=2.0)
    assert su._signed_margin(below) == -6.33
    assert su._signed_margin(above) == 0.34


# ------------------------------------------- 30 Sep: an open year's credit, at run-rate


def _series(open_average: float) -> dict[int, dict[str, Any]]:
    """GA-016's new shape: a TY2023 base, two qualifying years, TY2026 open."""
    statute = {"threshold": 2.0, "per_job_usd": 3500.0, "tranche_years": 5}
    return {
        2023: {"average_headcount": 12.0, "is_base_year": True, "status": "base", **statute},
        2024: {"average_headcount": 15.5, "status": "above_minimum", **statute},
        2025: {"average_headcount": 16.0, "status": "above_minimum", **statute},
        2026: {"average_headcount": open_average, "status": "in_progress", "months_reachable": 7, **statute},
    }


def test_an_open_year_at_run_rate_is_priced_as_a_closed_year_at_that_average():
    """The run-rate is `unit_trend` over the series with the to-date average
    standing in for the year — checked here against unit_trend called directly."""
    expected = unit_trend(
        {2023: {"average_headcount": 12.0}, 2024: {"average_headcount": 15.5},
         2025: {"average_headcount": 16.0}, 2026: {"average_headcount": 17.0}},
        state="GA", base_year=2023, threshold=2.0, per_job_usd=3500.0, tranche_years=5,
    )
    priced = next(y for y in expected.years if y.year == 2026).annual_credit_usd
    assert priced > 0
    assert su.run_rate_credit(_series(13.57), state="GA", tax_year=2026, base_year=2023, average=17.0) == round(priced)


def test_falling_behind_costs_the_tranches_already_earned():
    """Under the line so far, the run-rate is lower than on it: the jobs behind
    TY2024's tranche are not maintained, and that is credit at stake."""
    behind = su.run_rate_credit(_series(13.57), state="GA", tax_year=2026, base_year=2023)
    caught_up = su.run_rate_credit(_series(13.57), state="GA", tax_year=2026, base_year=2023, average=16.0)
    assert 0 <= behind < caught_up


def test_a_closed_year_has_no_run_rate():
    series = _series(13.57)
    assert su.run_rate_credit(series, state="GA", tax_year=2025, base_year=2023) is None
