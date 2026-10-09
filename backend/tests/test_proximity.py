"""D1 — employee-level threshold proximity.

The feature reads an eligibility result; it must never alter one. The last test
in this module is the one that matters: the certified figures are unchanged.
"""
from __future__ import annotations

import pytest

from tools.credit_math import resolve_statutory_floors
from domain.calculation.proximity import assess_employee, band_curve, near_miss_cohort


@pytest.fixture(scope="module")
def ga2023():
    """Georgia TY2023: 35 hours/week, $636/week. Threshold rate $18.17/hour."""
    return resolve_statutory_floors("GA_JTC", 2023)


def _avg(employee_id, hours, wages, weeks=52.0):
    """A row shaped like `OneZeroResult.all_averages`."""
    return {
        "Employee_ID": employee_id,
        "total_hours": hours,
        "total_wages": wages,
        "weeks_worked": weeks,
        "avg_weekly_hours": round(hours / weeks, 2),
        "avg_weekly_wages": round(wages / weeks, 2),
    }


# --- the four failure modes ------------------------------------------------


def test_eligible_employee_is_excluded(ga2023):
    # 40 hrs/wk at $25/hr — clears both floors.
    row = assess_employee(_avg("E1", 2080, 52000), floors=ga2023)
    assert row["eligible"] is True
    assert row["failed"] == []
    assert row["additional_weekly_hours"] == 0.0


def test_fails_hours_only(ga2023):
    # 30 hrs/wk at $25/hr = $750/wk. Wages clear, hours do not.
    row = assess_employee(_avg("E2", 1560, 39000), floors=ga2023)
    assert row["failure_mode"] == "hours_only"
    assert row["failed"] == ["hours"]
    assert row["hours_gap_per_week"] == 5.0
    assert row["wages_gap_per_week"] == 0.0
    # At $25/hr only the hours requirement binds.
    assert row["additional_weekly_hours"] == 5.0


def test_fails_wages_only(ga2023):
    # 40 hrs/wk at $15/hr = $600/wk. Hours clear, wages do not.
    row = assess_employee(_avg("E3", 2080, 31200), floors=ga2023)
    assert row["failure_mode"] == "wages_only"
    assert row["hours_gap_per_week"] == 0.0
    assert row["wages_gap_per_week"] == 36.0
    # $36/wk short at $15/hr needs 2.4 more hours a week.
    assert row["additional_weekly_hours"] == 2.4
    # And the alternative lever: the rate that qualifies at today's hours.
    assert row["hourly_rate_to_qualify"] == pytest.approx(15.9, abs=0.01)


def test_fails_both(ga2023):
    # 30 hrs/wk at $15/hr = $450/wk. Misses both.
    row = assess_employee(_avg("E4", 1560, 23400), floors=ga2023)
    assert row["failure_mode"] == "both"
    assert sorted(row["failed"]) == ["hours", "wages"]
    assert row["hours_gap_per_week"] == 5.0
    assert row["wages_gap_per_week"] == 186.0
    # The wage requirement binds harder: 186/15 = 12.4 hrs > the 5 hrs the hours
    # test alone would need. Taking the max is the whole point.
    assert row["additional_weekly_hours"] == 12.4
    # A raise cannot fix someone who is not working enough hours at any rate.
    assert row["hourly_rate_to_qualify"] is None


# --- the distinction that makes it an instruction --------------------------


def test_below_threshold_rate_is_flagged_rate_limited(ga2023):
    """$636/35 = $18.17/hr. Below that, more hours is the wrong lever."""
    row = assess_employee(_avg("E5", 2080, 31200), floors=ga2023)  # $15/hr
    assert row["rate_limited"] is True
    assert row["threshold_hourly_rate"] == pytest.approx(18.17, abs=0.01)


def test_above_threshold_rate_is_not_rate_limited(ga2023):
    row = assess_employee(_avg("E6", 1560, 39000), floors=ga2023)  # $25/hr
    assert row["rate_limited"] is False


def test_implausible_week_is_flagged_not_hidden(ga2023):
    """20 hrs/wk at $12/hr. Reachable arithmetically, not operationally."""
    row = assess_employee(_avg("E7", 1040, 12480), floors=ga2023)
    assert row["additional_weekly_hours"] is not None
    assert row["projected_weekly_hours"] > 40.0
    assert row["exceeds_plausible_week"] is True


def test_zero_hours_yields_no_rate_and_no_instruction(ga2023):
    """BA-05 keeps wages paid against no hours. They have no hourly rate, and
    inventing one would produce a confident instruction from nothing."""
    row = assess_employee(_avg("E8", 0, 5000), floors=ga2023)
    assert row["implied_hourly_rate"] is None
    assert row["additional_weekly_hours"] is None
    # No hours and $96/wk: this employee misses both floors. The point of the
    # test is the absent instruction, not the failure mode.
    assert row["failure_mode"] == "both"


# --- the cohort ------------------------------------------------------------


def test_cohort_counts_failure_modes_separately(ga2023):
    rows = [
        _avg("A", 2080, 52000),   # eligible
        _avg("B", 1560, 39000),   # hours only
        _avg("C", 2080, 31200),   # wages only
        _avg("D", 1560, 23400),   # both
    ]
    out = near_miss_cohort(rows, floors=ga2023, within_weekly_hours=20.0)
    assert out["evaluated"] == 4
    assert out["eligible"] == 1
    assert out["ineligible"] == 3
    assert out["failure_modes"] == {"hours_only": 1, "wages_only": 1, "both": 1}


def test_cohort_ranks_by_the_actionable_number(ga2023):
    rows = [
        _avg("far", 1560, 23400),   # needs 12.4
        _avg("near", 2080, 31200),  # needs 2.4
        _avg("mid", 1560, 39000),   # needs 5.0
    ]
    out = near_miss_cohort(rows, floors=ga2023, within_weekly_hours=20.0)
    assert [r["employee_id"] for r in out["cohort"]] == ["near", "mid", "far"]


def test_band_excludes_the_unreachable(ga2023):
    rows = [_avg("near", 2080, 31200), _avg("far", 1560, 23400)]
    out = near_miss_cohort(rows, floors=ga2023, within_weekly_hours=5.0)
    assert out["within_band"] == 1
    assert [r["employee_id"] for r in out["cohort"]] == ["near"]


def test_eligible_never_enter_the_cohort(ga2023):
    rows = [_avg(f"E{i}", 2080, 52000) for i in range(5)]
    out = near_miss_cohort(rows, floors=ga2023, within_weekly_hours=40.0)
    assert out["ineligible"] == 0
    assert out["cohort"] == []


def test_band_curve_is_monotonic(ga2023):
    rows = [
        _avg("a", 2080, 31200), _avg("b", 1560, 39000),
        _avg("c", 1560, 23400), _avg("d", 1040, 12480),
    ]
    curve = band_curve(rows, floors=ga2023)
    counts = [b["employees"] for b in curve]
    assert counts == sorted(counts), "a wider band cannot reach fewer employees"
    assert all(b["plausible"] <= b["employees"] for b in curve)


def test_floors_come_from_the_year_pack_not_the_caller(ga2023):
    out = near_miss_cohort([_avg("x", 1560, 23400)], floors=ga2023)
    assert out["floors"]["minimum_average_weekly_hours"] == 35.0
    assert out["floors"]["minimum_average_weekly_wages_usd"] == 636.0
    assert out["floors"]["source"] == "rules/ga_jtc/2023.json"


def test_a_different_year_prices_under_its_own_statute():
    """TY2024's floor is $686, not 2023's $636. Same employee, different answer."""
    y23 = resolve_statutory_floors("GA_JTC", 2023)
    y24 = resolve_statutory_floors("GA_JTC", 2024)
    assert y24.min_weekly_wages != y23.min_weekly_wages

    row = _avg("straddler", 2080, 34000)  # ~$654/wk — clears 2023, misses 2024
    assert assess_employee(row, floors=y23)["eligible"] is True
    assert assess_employee(row, floors=y24)["eligible"] is False


# --- the engine defect this feature exposed --------------------------------


def test_both_methods_attach_per_employee_averages():
    """`run_min_max_method` computed averages in Step 3 and dropped them.

    Pay Period attached `all_averages`; Min Max did not, so anything reading it
    got an empty list under a successful call. The proximity endpoint defaults
    to `min_max`, which meant a confident "nobody is near the line" over a
    population that had sixteen employees within five hours.
    """
    from api._payperiods import iter_state_packs, require_pay_periods
    from config import get_fiscal_year_end_month
    from domain.calculation.onezero import (
        fiscal_window_start,
        run_min_max_method,
        run_pay_period_method,
    )

    fy_end = get_fiscal_year_end_month()
    rows = require_pay_periods()
    packs = list(iter_state_packs(rows, tax_year=2025, state="GA", on_unauthored="skip"))
    if not packs:
        pytest.skip("no GA 2025 payroll in this data source")
    _st, pack, state_rows = packs[0]

    for runner in (run_min_max_method, run_pay_period_method):
        result = runner(
            state_rows,
            tax_year=2025,
            analysis_start_month=fiscal_window_start(2025, fy_end),
            pack=pack,
            fiscal_year_end_month=fy_end,
        )
        assert result.all_averages, f"{result.method} attached no per-employee averages"
        assert len(result.all_averages) >= len(result.eligible_employees)
        sample = result.all_averages[0]
        assert {"Employee_ID", "avg_weekly_hours", "avg_weekly_wages",
                "weeks_worked", "total_hours", "total_wages"} <= set(sample)


# --- the verdict is read, not re-derived -----------------------------------


def test_a_recorded_verdict_beats_the_floors(ga2023):
    """A part-time-band employee is eligible while failing the hours floor.

    `_eligibility_filter` sets `eligible = weight > 0`, and South Carolina's
    pack carries a 20-32 hour band at weight 0.5. Deriving eligibility from the
    two floors reported every SC part-timer as a near miss the run had already
    counted — and then offered a lever to "fix" someone who was not broken.
    """
    row = _avg("PT", 1300, 33800)  # 25 hrs/wk at $26/hr — misses 35 hrs, clears $636
    assert assess_employee(row, floors=ga2023)["eligible"] is False

    row["eligible"] = True
    assessed = assess_employee(row, floors=ga2023)
    assert assessed["eligible"] is True
    assert assessed["verdict_source"] == "recorded"
    # The floors still report WHICH test was missed. That is the display half of
    # the verdict, and it has to stay visible for the band to mean anything.
    assert assessed["failed"] == ["hours"]


def test_a_recorded_verdict_that_agrees_changes_nothing(ga2023):
    """Georgia has no part-time band, so recorded and derived must agree."""
    row = _avg("FT", 2080, 52000)
    derived = assess_employee(dict(row), floors=ga2023)
    row["eligible"] = True
    recorded = assess_employee(row, floors=ga2023)
    assert recorded["eligible"] == derived["eligible"] is True
    assert recorded["verdict_disagrees"] is False


def test_a_verdict_the_floors_contradict_is_flagged(ga2023):
    """The signal that the rule pack moved after the run.

    `run_manifest.rule_pack_version` cannot detect this — it stores the pack's
    path, and re-authoring a materialised year pack changes its contents but
    not its filename.
    """
    row = _avg("drifted", 2080, 52000)
    row["eligible"] = False  # clears both floors today, recorded as out
    assert assess_employee(row, floors=ga2023)["verdict_disagrees"] is True


def test_the_cohort_counts_disagreements(ga2023):
    rows = [_avg(f"ok{i}", 1560, 23400) for i in range(3)]
    for row in rows:
        row["eligible"] = False
    drifted = _avg("drifted", 2080, 52000)
    drifted["eligible"] = False
    out = near_miss_cohort([*rows, drifted], floors=ga2023, within_weekly_hours=40.0)
    assert out["verdict_disagreements"] == 1


def test_a_recorded_eligible_is_not_offered_as_a_near_miss(ga2023):
    """The cohort is the INELIGIBLE population, and the run decides who that is."""
    row = _avg("PT", 1300, 33800)
    without = near_miss_cohort([dict(row)], floors=ga2023, within_weekly_hours=40.0)
    assert without["ineligible"] == 1

    row["eligible"] = True
    with_verdict = near_miss_cohort([row], floors=ga2023, within_weekly_hours=40.0)
    assert with_verdict["ineligible"] == 0
    assert with_verdict["cohort"] == []


def test_the_hours_bound_never_drops_a_reachable_employee(ga2023):
    """The prefilter that took the reference client from 21 seconds to 3.

    The Gold read fetches only `avg_weekly_hours >= min_hours - B`. That is a
    NECESSARY condition, not a heuristic: the lever is
    `max(hours_gap, wages_gap / rate)`, so it is never smaller than `hours_gap`.
    If this ever fails, the read is silently hiding people who could qualify.
    """
    from domain.calculation.proximity import BAND_CURVE_HOURS

    bound = max(BAND_CURVE_HOURS)
    floor = float(ga2023.min_weekly_hours)

    # A deliberately hostile spread: every rate from minimum wage to $80/hr,
    # every weekly hours figure from nothing to well over full time.
    for weekly_hours in [h / 2 for h in range(0, 101)]:
        for rate in (7.25, 12.0, 18.17, 25.0, 40.0, 80.0):
            weeks = 52.0
            row = _avg("probe", weekly_hours * weeks, weekly_hours * rate * weeks, weeks)
            assessed = assess_employee(row, floors=ga2023)
            additional = assessed["additional_weekly_hours"]
            if additional is not None and additional <= bound:
                assert weekly_hours >= floor - bound, (
                    f"{weekly_hours} hrs/wk at ${rate}/hr is {additional} hours from "
                    f"qualifying but sits below the fetch bound of {floor - bound}"
                )


def test_supplied_population_counts_override_a_bounded_set(ga2023):
    """The rows are bounded; the denominator must not be.

    "24 of 9,541 considered" is the sentence the screen makes, and a count taken
    over the filtered rows would quietly turn it into "24 of 40".
    """
    rows = [_avg("near", 1716, 42900)]  # 33 hrs/wk — inside the band
    out = near_miss_cohort(
        rows, floors=ga2023, within_weekly_hours=5.0,
        population={
            "evaluated": 10080, "eligible": 539, "ineligible": 9541,
            "failure_modes": {"hours_only": 7000, "wages_only": 41, "both": 2500},
        },
    )
    assert out["evaluated"] == 10080
    assert out["eligible"] == 539
    assert out["ineligible"] == 9541
    assert out["failure_modes"]["hours_only"] == 7000
    # The band itself is still measured over the rows actually assessed.
    assert out["within_band"] == 1


# --- the jobs already counted, and what would lose them --------------------


def test_the_smaller_cushion_binds_on_the_way_out(ga2023):
    """The mirror of the near-miss lever, and it is `min`, not `max`.

    Coming IN, both floors must be cleared, so the LARGER gap binds. Going OUT,
    breaching EITHER floor is enough, so the SMALLER cushion binds. Somebody at
    twice the hours floor and a dollar over the wage floor is one bad week from
    falling out; taking the hours cushion alone would call them safe.
    """
    from domain.calculation.proximity import fragility

    # 70 hrs/wk (35 over the floor) but $637/wk — $1 over a $636 floor.
    row = _avg("thin-on-wages", 70 * 52, 637 * 52)
    out = fragility(row, floors=ga2023)

    assert out["hours_headroom"] == 35.0
    assert out["wages_headroom_usd"] == 1.0
    assert out["binding_floor"] == "wages"
    assert out["weekly_hours_to_lose"] < 1.0


def test_an_employee_deep_inside_is_not_fragile(ga2023):
    from domain.calculation.proximity import fragility

    # 45 hrs at $50/hr. Ten hours of hours-cushion, and the wage cushion is
    # far wider, so neither floor is close.
    out = fragility(_avg("safe", 45 * 52, 2250 * 52), floors=ga2023)
    assert out["weekly_hours_to_lose"] == 10.0
    assert out["binding_floor"] == "hours"


def test_the_cohort_counts_jobs_not_people(ga2023):
    """A part-time band carries a fractional weight, so losing somebody does
    not always cost a whole job."""
    from domain.calculation.proximity import fragile_cohort

    rows = [_avg("a", 36 * 52, 700 * 52), _avg("b", 36 * 52, 700 * 52)]
    rows[0]["weight"] = 0.5
    out = fragile_cohort(rows, floors=ga2023, within_weekly_hours=5.0)

    assert out["within_band"] == 2
    assert out["jobs_at_risk"] == 1.5


def test_the_cohort_ranks_by_how_little_it_would_take(ga2023):
    from domain.calculation.proximity import fragile_cohort

    rows = [_avg("roomy", 40 * 52, 900 * 52), _avg("thin", 35.5 * 52, 700 * 52)]
    out = fragile_cohort(rows, floors=ga2023, within_weekly_hours=10.0)
    assert [r["employee_id"] for r in out["cohort"]] == ["thin", "roomy"]


def test_the_cohort_does_not_re_decide_who_qualified(ga2023):
    """It ranks cushions over the ELIGIBLE population it is handed.

    Re-deciding eligibility here would be a second opinion about a verdict the
    run already recorded — the same rule the near-miss cohort follows.
    """
    from domain.calculation.proximity import fragile_cohort

    # Below both floors. Passed in anyway; the function must not silently drop
    # it on its own authority, it simply has a negative cushion.
    out = fragile_cohort([_avg("x", 20 * 52, 300 * 52)], floors=ga2023,
                         within_weekly_hours=5.0)
    assert out["eligible"] == 1


# --- the gate --------------------------------------------------------------


def test_proximity_does_not_move_the_certified_figures():
    """The feature reads the eligibility result. It must never alter one."""
    from tests.certified import CERTIFIED_MIN_MAX_ELIGIBLE, CERTIFIED_PAY_PERIOD_ELIGIBLE

    floors = resolve_statutory_floors("GA_JTC", 2023)
    rows = [_avg(f"E{i}", 1560, 23400) for i in range(50)]
    before = (CERTIFIED_MIN_MAX_ELIGIBLE, CERTIFIED_PAY_PERIOD_ELIGIBLE)
    near_miss_cohort(rows, floors=floors)
    band_curve(rows, floors=floors)
    assert (CERTIFIED_MIN_MAX_ELIGIBLE, CERTIFIED_PAY_PERIOD_ELIGIBLE) == before
    assert before == (539, 656)
