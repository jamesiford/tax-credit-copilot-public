"""The unit read carries two cohorts, and they are different answers.

`onezero_matrix` holds ONLY employees who already qualified, so any cusp count
derived from it is structurally zero — it was, at every unit on every client.
The people one shift short live in `employee_eligibility`, which has no
worksite; `employee_period_fact` is what places them.

Live-Fabric and opt-in: these assert against real warehouse rows, so they prove
the SQL rather than a stand-in's opinion of it.
"""
from __future__ import annotations

import os

import pytest

CASCADE = 2001
YEAR = 2023
METHOD = "min_max"


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture()
def reader():
    _requires_fabric()
    from infrastructure.persistence.gold_reader import GoldReader

    return GoldReader()


@pytest.fixture()
def run(reader):
    live = reader.latest_run(CASCADE)
    if live is None:
        pytest.skip(f"no successful run for client {CASCADE} TY{YEAR}")
    return live


def test_the_eligibility_join_does_not_fan_out(reader, run):
    """One eligibility row per (token, method, run), so the count must not move.

    A LEFT JOIN that duplicated would inflate a headcount silently — the page
    would show more people at a location than the statute counted, which is the
    same class of error as the month filter that annotated instead of narrowing.
    """
    rows = reader.unit_employees(
        CASCADE, "GA_GA-001", tax_year=YEAR, method=METHOD, run_id=run["run_id"]
    )
    tokens = [row["record_token"] for row in rows]
    assert len(tokens) == len(set(tokens)), "the join fanned out"
    assert len(rows) == 29


def test_the_join_carries_the_hours_the_matrix_does_not_hold(reader, run):
    rows = reader.unit_employees(
        CASCADE, "GA_GA-001", tax_year=YEAR, method=METHOD, run_id=run["run_id"]
    )
    assert rows, "expected a populated unit"
    assert all(row["avg_weekly_hours"] is not None for row in rows)
    # Sorted by effort, so the page does not have to re-rank what SQL ordered.
    hours = [float(row["avg_weekly_hours"]) for row in rows]
    assert hours == sorted(hours, reverse=True)


def _within(rows, floor=35.0, band=5.0):
    """The band is applied by the CALLER, not by SQL.

    The reader returns every ineligible employee at the unit; how close counts
    as close is a presentation choice, and baking 35 into the query would put
    Georgia's floor in everyone's warehouse read.
    """
    return [
        row for row in rows
        if row["avg_weekly_hours"] is not None
        and float(row["avg_weekly_hours"]) >= floor - band
    ]


def test_the_near_threshold_cohort_is_not_empty(reader, run):
    """The whole point: a cusp count taken from the matrix is always zero.

    GA_GA-010 carries the largest near-miss cohort at Cascade. If this returns
    an empty list the join has silently reverted to reading only the qualified.
    """
    near = reader.unit_near_threshold(
        CASCADE, "GA_GA-010", tax_year=YEAR, method=METHOD, run_id=run["run_id"]
    )
    assert len(near) == 11
    assert len(_within(near)) == 8


def test_the_near_threshold_cohort_holds_nobody_who_qualified(reader, run):
    qualified = {
        row["record_token"]
        for row in reader.unit_employees(
            CASCADE, "GA_GA-001", tax_year=YEAR, method=METHOD, run_id=run["run_id"]
        )
    }
    near = reader.unit_near_threshold(
        CASCADE, "GA_GA-001", tax_year=YEAR, method=METHOD, run_id=run["run_id"]
    )
    assert len(near) == 7
    assert len(_within(near)) == 4
    assert not (qualified & {row["record_token"] for row in near})
    # The closest miss at this unit, which is what makes the band actionable.
    assert max(float(row["avg_weekly_hours"]) for row in near) == pytest.approx(34.81, abs=0.01)


def test_the_near_threshold_cohort_does_not_duplicate_a_person(reader, run):
    """`employee_period_fact` is one row per pay period; DISTINCT is load-bearing."""
    near = reader.unit_near_threshold(
        CASCADE, "GA_GA-007", tax_year=YEAR, method=METHOD, run_id=run["run_id"]
    )
    tokens = [row["record_token"] for row in near]
    assert len(tokens) == len(set(tokens))
    assert len(tokens) == 9
    assert len(_within(near)) == 6


def test_the_floor_is_returned_as_a_number_not_a_version_string():
    """A marker cannot be drawn at `ga_jtc@2023`."""
    _requires_fabric()
    from api.trend import _unit_thresholds

    floors = _unit_thresholds("GA_JTC", YEAR)
    assert floors["resolved"] is True
    assert floors["min_weekly_hours"] == 35.0
    assert isinstance(floors["min_weekly_hours"], float)
    assert floors["min_weekly_wages"] > 0
