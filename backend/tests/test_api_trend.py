"""The per-unit trend, and the one thing it must never do quietly.

The grid this feeds is the first screen an operator sees, so its numbers get
quoted. Two failure modes matter more than the rest:

- **Disagreeing with the single-year read.** A unit's twelve monthly columns for
  a tax year have to be the same columns `/api/onezero/matrix/{year}` publishes
  for that unit, or the landing screen and the drill-in tell different stories
  about the same location.
- **A silent hole.** A year the statute cannot price must be declined by name.
  Dropped from the series it reads as a flat year, and a flat year is a finding
  somebody will act on.
"""
from __future__ import annotations

import os

import pytest

from application.queries._client_run import ClientRunNotAvailable
from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery
from application.queries.get_unit_trend import GetUnitTrendQuery
from tools.unit_trend import (
    MONTHS_IN_YEAR,
    STATUS_ABOVE,
    STATUS_BASE,
    STATUS_BELOW,
    STATUS_NO_DATA,
    STATUS_PARTIAL,
    aggregate_units,
    infer_base_year,
    unit_status,
)

_STATUSES = {STATUS_BASE, STATUS_ABOVE, STATUS_BELOW, STATUS_PARTIAL, STATUS_NO_DATA}


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def lakehouse_source(monkeypatch):
    """`conftest.py` pins DATA_SOURCE=csv suite-wide; multi-client reads need lakehouse."""
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")


# --- the pure reshaping: cheap and offline -----------------------------------


def _near_row(**kwargs):
    base = {"employee_id": "E1", "weeks_worked": 52.0}
    return {**base, **kwargs}


def test_the_hours_lever_is_larger_than_the_hours_gap_when_wages_bind():
    """The partner asks "how many more hours a week would Sally need to work?".

    The grid already shows the hours gap, and for most people that IS the
    answer. It is not the answer for somebody clearing the hours floor and
    failing the wage floor: they need extra hours priced at their OWN rate, so
    the binding requirement is the larger of the two. Reporting the hours gap
    alone tells that person they are fine.
    """
    from api.trend import _with_lever

    rows = [
        # Short on hours, comfortably over on wages. GA TY2023 is 35 hrs / $636.
        _near_row(
            employee_id="E-HOURS",
            avg_weekly_hours=34.29, avg_weekly_wages=700.0,
            total_hours=1783.08, total_wages=36400.0,
        ),
        # OVER on hours and under on wages at $13.89/hr. The hours gap is zero.
        _near_row(
            employee_id="E-WAGES",
            avg_weekly_hours=36.0, avg_weekly_wages=500.0,
            total_hours=1872.0, total_wages=26000.0,
        ),
    ]

    by_id = {r["employee_id"]: r for r in _with_lever(rows, "GA_JTC", 2023)}

    assert by_id["E-HOURS"]["additional_weekly_hours"] == 0.71
    assert by_id["E-HOURS"]["failure_mode"] == "hours_only"

    wages = by_id["E-WAGES"]
    assert wages["failure_mode"] == "wages_only"
    # The whole point: 36 hrs is ABOVE the 35-hour floor, so the visible gap is
    # nothing at all, and the real lever is nearly ten hours.
    assert wages["additional_weekly_hours"] == 9.79
    assert wages["avg_weekly_hours"] > 35.0
    # The alternative lever, for a conversation about pay rather than schedule.
    assert wages["hourly_rate_to_qualify"] is not None


def test_the_lever_names_a_week_nobody_works_rather_than_offering_it():
    """A 90-hour week is not a lever.

    The difference between a work list and a list of impossibilities.
    """
    from api.trend import _with_lever

    rows = [_near_row(
        employee_id="E-IMPOSSIBLE",
        avg_weekly_hours=8.0, avg_weekly_wages=60.0,
        total_hours=416.0, total_wages=3120.0,
    )]
    lever = _with_lever(rows, "GA_JTC", 2023)[0]
    assert lever["exceeds_plausible_week"] is True


def test_no_lever_is_invented_for_a_year_the_statute_cannot_price():
    """An unauthored year has no floor, so it has no distance from one.

    Returning the rows untouched is what lets the grid render a dash. Inventing
    a floor to measure against would put a specific, wrong number on screen.
    """
    from api.trend import _with_lever

    rows = [_near_row(avg_weekly_hours=10.0, avg_weekly_wages=100.0,
                      total_hours=520.0, total_wages=5200.0)]
    assert _with_lever(rows, None, 2023) == rows
    assert _with_lever(rows, "GA_JTC", 1999) == rows


def test_the_lever_never_reports_a_dollar_value_per_employee():
    """A location's credit turns on its job count against a threshold.

    The marginal employee is worth the whole tranche if they cross it and
    nothing at all if they do not, so no per-person dollar figure is honest.
    The one money field is a RATE — what to pay them — not a credit value.
    """
    from api.trend import _with_lever

    rows = [_near_row(avg_weekly_hours=36.0, avg_weekly_wages=500.0,
                      total_hours=1872.0, total_wages=26000.0)]
    added = set(_with_lever(rows, "GA_JTC", 2023)[0]) - set(rows[0])
    assert added == {
        "additional_weekly_hours", "projected_weekly_hours",
        "exceeds_plausible_week", "failure_mode", "hourly_rate_to_qualify",
    }
    assert not any("credit" in key or "usd" in key for key in added)


def test_a_location_hosting_two_entities_is_tested_as_one_location():
    """Georgia tests headcount at the location; FEIN is a filing detail."""
    units = aggregate_units(
        [
            {"unit_id": "GA_A", "fein": "58-1", "month_totals": [1] * MONTHS_IN_YEAR},
            {"unit_id": "GA_A", "fein": "58-2", "month_totals": [2] * MONTHS_IN_YEAR},
        ]
    )

    assert len(units) == 1
    assert units[0]["month_totals"] == [3.0] * MONTHS_IN_YEAR
    assert units[0]["average_headcount"] == 3.0
    assert units[0]["feins"] == ["58-1", "58-2"]


def test_a_partial_year_does_not_become_a_flattering_base():
    """Six months averaged over twelve reads as half the headcount it was."""
    unit_years = {
        2021: {"months_with_headcount": 6, "average_headcount": 5.0},
        2022: {"months_with_headcount": 12, "average_headcount": 10.0},
    }

    assert infer_base_year(unit_years) == 2022


def test_the_base_year_falls_back_only_when_no_year_is_complete():
    unit_years = {
        2021: {"months_with_headcount": 6, "average_headcount": 5.0},
        2022: {"months_with_headcount": 9, "average_headcount": 7.0},
    }

    assert infer_base_year(unit_years) == 2021


def test_a_year_is_complete_when_it_fills_every_month_that_is_reachable():
    """A calendar-year client whose last December period ends on the 15th has no
    measuring date in December, so eleven months IS its complete year.

    Judging it against twelve rejected a complete year and pushed the base a
    year later. The base is the most leveraged input in the model, so that
    changed every net-new figure and every dollar downstream.
    """
    unit_years = {
        2020: {"months_with_headcount": 11, "average_headcount": 18.3},
        2021: {"months_with_headcount": 12, "average_headcount": 25.5},
    }

    assert infer_base_year(unit_years) == 2021
    assert infer_base_year(unit_years, reachable_by_year={2020: 11, 2021: 12}) == 2020


def test_an_unreachable_final_month_is_not_reported_as_a_short_year():
    """`partial` means the payroll does not cover the year. This one does."""
    complete = dict(tax_year=2020, base_year=2019, qualified=True, months_with_headcount=11)

    assert unit_status(**complete) == STATUS_PARTIAL
    assert unit_status(**complete, months_reachable=11) == STATUS_ABOVE


def test_every_reading_is_one_of_the_five_the_grid_can_colour():
    cases = [
        dict(tax_year=2021, base_year=2021, qualified=True, months_with_headcount=12),
        dict(tax_year=2022, base_year=2021, qualified=True, months_with_headcount=12),
        dict(tax_year=2022, base_year=2021, qualified=False, months_with_headcount=12),
        dict(tax_year=2022, base_year=2021, qualified=True, months_with_headcount=7),
        dict(tax_year=2022, base_year=2021, qualified=True, months_with_headcount=0),
    ]

    assert [unit_status(**case) for case in cases] == [
        STATUS_BASE, STATUS_ABOVE, STATUS_BELOW, STATUS_PARTIAL, STATUS_NO_DATA
    ]


def test_method_must_be_one_the_engine_actually_runs():
    with pytest.raises(ValueError, match="method must be one of"):
        GetUnitTrendQuery(state="GA", method="minmax")


def test_a_state_with_no_authored_statute_is_declined_not_trended():
    """[ADR-005] A trend needs a statute to test each year against."""
    from application.wiring import get_mediator

    with pytest.raises(ClientRunNotAvailable):
        get_mediator().send(GetUnitTrendQuery(state="ZZ"))


# --- the read, against the local fixture -------------------------------------


def test_the_trend_reports_a_base_year_and_a_reading_for_every_row():
    from application.wiring import get_mediator

    body = get_mediator().send(GetUnitTrendQuery(state="GA"))

    assert body["units"], "the fixture client has Georgia worksites"
    for unit in body["units"]:
        assert unit["base_year"] in body["years"]
        assert unit["base_year_source"] in ("inferred", "override")
        base_rows = [row for row in unit["rows"] if row["is_base_year"]]
        assert len(base_rows) == 1
        assert base_rows[0]["status"] == STATUS_BASE
        for row in unit["rows"]:
            assert row["status"] in _STATUSES
            assert len(row["month_totals"]) == MONTHS_IN_YEAR


def test_an_unregistered_unit_is_unassigned_rather_than_guessed_a_tier():
    """A guessed tier moves the threshold, and therefore whether a year qualifies."""
    from application.wiring import get_mediator

    body = get_mediator().send(GetUnitTrendQuery(state="GA"))

    for unit in body["units"]:
        for row in unit["rows"]:
            assert row["tier_source"] in ("prototype", "unassigned")
            if row["tier_source"] == "unassigned":
                assert row["tier"] is None


def test_the_screen_says_what_it_cannot_stand_behind():
    from application.wiring import get_mediator

    body = get_mediator().send(GetUnitTrendQuery(state="GA"))
    codes = {d["code"] for d in body["disclosures"]}

    assert {"DISC-8", "DISC-10", "TIER-FLAT"} <= codes


def test_the_grid_and_the_drill_index_the_same_months(lakehouse_source):
    """The drill opens a month by POSITION, so the two must agree on the grid.

    The grid sums a year's columns; the drawer filters the matrix by the index
    of the column that was clicked. If the two ever disagreed about which month
    position 3 is, the drawer would name the wrong people with total confidence.

    Live-Fabric since the matrix became a Gold read: the grid still replays the
    engine, so this now checks that what a run WROTE indexes the same months the
    engine produces.
    """
    from application.wiring import get_mediator

    mediator = get_mediator()
    trend = mediator.send(GetUnitTrendQuery(state="GA", account_id=1001))

    checked = 0
    for meta in trend["year_meta"]:
        matrix = mediator.send(GetOneZeroMatrixQuery(
            tax_year=meta["tax_year"], state="GA", method="min_max", account_id=1001,
        ))
        assert len(meta["months"]) == MONTHS_IN_YEAR
        # Gold holds one year for the reference client; the rest decline, and a
        # declined year has no months to disagree about.
        if matrix["calculation_state"] != "calculated":
            continue
        assert meta["months"] == matrix["months"]
        checked += 1

    assert checked, "no calculated year to compare; the check did not run"


def test_a_second_read_is_served_without_replaying_the_engine():
    """The landing screen is opened for every client; the replay is not cheap."""
    from application.queries.get_unit_trend import _REPLAY_CACHE, reset_replay_cache
    from application.wiring import get_mediator

    reset_replay_cache()
    mediator = get_mediator()
    first = mediator.send(GetUnitTrendQuery(state="GA"))
    assert len(_REPLAY_CACHE) == 1

    second = mediator.send(GetUnitTrendQuery(state="GA"))
    assert second["units"] == first["units"]
    reset_replay_cache()


# --- the join between the landing screen and the drill-in --------------------


@pytest.mark.parametrize("method", ["min_max", "pay_period"])
def test_a_units_monthly_columns_match_the_single_year_matrix(lakehouse_source, method):
    """The landing grid and the drill-in must describe the same location."""
    from application.wiring import get_mediator

    mediator = get_mediator()
    trend = mediator.send(
        GetUnitTrendQuery(state="GA", account_id=1001, method=method)
    )
    tax_year = 2023
    assert tax_year in trend["years"]

    matrix = mediator.send(
        GetOneZeroMatrixQuery(
            tax_year=tax_year, state="GA", account_id=1001, method=method
        )
    )

    expected: dict[str, list[float]] = {}
    for row in matrix["summary"]:
        columns = expected.setdefault(row["unit_id"], [0.0] * MONTHS_IN_YEAR)
        for index, value in enumerate(row["month_totals"][:MONTHS_IN_YEAR]):
            columns[index] += value

    for unit in trend["units"]:
        row = next((r for r in unit["rows"] if r["tax_year"] == tax_year), None)
        if row is None:
            continue
        assert unit["unit_id"] in expected
        assert row["month_totals"] == pytest.approx(expected[unit["unit_id"]], abs=0.01)


def test_a_year_the_statute_cannot_price_is_named_not_dropped(lakehouse_source):
    from application.wiring import get_mediator

    body = get_mediator().send(GetUnitTrendQuery(state="GA", account_id=1001))

    for decline in body["declined_years"]:
        assert decline["reason"], "a declined year has to say why"
        assert int(decline["tax_year"]) not in body["years"]
