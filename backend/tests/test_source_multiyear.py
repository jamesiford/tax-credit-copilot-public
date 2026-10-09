"""The six-year window, and whether each synthetic client still tells its story.

`synth.py` exists to exercise the retroactive audit: a frozen base year, a
persistent high-water mark, backfill, and five-year tranches. Those mechanics
only get tested if the generated payroll actually has the right SHAPE, and shape
is easy to lose — a tweak to churn or wage growth can flatten a trajectory while
every structural test still passes and the demo quietly shows nothing.

So these tests assert the narrative, not just the plumbing:

    Cascade     grows every year and qualifies every year — GA-007 falls below
                the minimum from June TY2025, and GA-016 opens with TY2023,
                qualifies, then dips below in the open TY2026
    Northwind   falls below its frozen base, stops qualifying, then BACKFILLS
    Ironbridge  spends a year with net-new above zero but under the statutory
                minimum — qualifying for nothing, which is the "you could have
                claimed from 2023" pitch
    Halloway    qualifies early, then stops, while its high-water mark stays up
                and its early tranches are still in-window

There is also a guard on the eligible share. Georgia's floor climbed from $541
to $686 across this window; if wage growth ever falls far behind it, employees
drop out of eligibility with no job lost and the demo hollows out silently.
`test_eligible_share_does_not_collapse` turns that into a failure.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import pytest

from data.source.synth import (
    BASE_TAX_YEAR,
    SYNTHETIC_CLIENTS,
    WINDOW_YEARS,
    _shift_years,
    build_synthetic_dataset,
)
from data.source.to_bcs import source_to_bcs_rows
from tools.baseyear import compute_base_year_tranches
from tools.credit_math import (
    apply_one_zero_state_credit,
    load_pack_one_zero,
    resolve_statutory_floors,
)
from domain.calculation.onezero import run_pay_period_method

_BY_NAME = {spec.name: spec for spec in SYNTHETIC_CLIENTS}


@pytest.fixture(scope="module")
def datasets():
    return {spec.name: build_synthetic_dataset(spec) for spec in SYNTHETIC_CLIENTS}


def _ga_yearly_average(spec, dataset) -> dict[int, float]:
    """Average Headcount per tax year for the client's Georgia worksites.

    The fiscal window is passed explicitly rather than inferred. `fiscal_year_of`
    labels a fiscal year by the year it ENDS, while Georgia labels a tax year by
    the year it BEGINS — see `test_fiscal_year_label_matches_the_regulation`.
    Passing the window sidesteps that disagreement so these assertions are about
    the DATA rather than about the open labelling question.
    """
    rows = [r for r in source_to_bcs_rows(dataset) if r["Work_State"] == "GA"]
    yearly: dict[int, float] = {}
    for index, tax_year in enumerate(spec.tax_years):
        begin = _shift_years(spec.fiscal_begin, index)
        end = _shift_years(spec.fiscal_end, index)
        window = [r for r in rows if begin.isoformat() <= r["Pay_Date"] <= end.isoformat()]
        if not window:
            continue
        result = run_pay_period_method(
            window,
            tax_year=tax_year,
            analysis_start_month=begin,
            pack=load_pack_one_zero("GA", tax_year=tax_year),
            fiscal_window=(begin, end),
        )
        yearly[tax_year] = result.annual_average
    return yearly


def _tranches(spec, dataset):
    yearly = _ga_yearly_average(spec, dataset)
    assert len(yearly) >= 2, f"{spec.name}: needs at least two GA years"
    sample = apply_one_zero_state_credit("GA", yearly[max(yearly)])
    return compute_base_year_tranches(
        "GA",
        yearly,
        base_year=min(yearly),
        threshold=float(sample["threshold"]),
        per_job_usd=float(sample["amount_per_job_usd"]),
    )


# --------------------------------------------------------------- the window


@pytest.mark.parametrize("spec", SYNTHETIC_CLIENTS, ids=lambda s: s.name)
def test_every_client_spans_the_full_window(spec, datasets):
    dataset = datasets[spec.name]
    years = {p.pay_period_end.year for p in dataset.payroll}
    assert len(spec.tax_years) == WINDOW_YEARS
    assert spec.tax_years[0] == BASE_TAX_YEAR
    # Six fiscal years touch at least six calendar years.
    assert len(years) >= WINDOW_YEARS, f"{spec.name}: only {sorted(years)}"


@pytest.mark.parametrize("spec", SYNTHETIC_CLIENTS, ids=lambda s: s.name)
def test_every_authored_year_has_statute(spec, datasets):
    """Nothing is generated for a year the engine would have to refuse to price.

    Except for the tail of a non-calendar fiscal year, which legitimately spills
    into the next calendar year — that is the BA-02 boundary, not a defect.
    """
    for tax_year in spec.tax_years:
        floors = resolve_statutory_floors("GA_JTC", tax_year)
        assert floors.prototype_verify is False


@pytest.mark.parametrize("spec", SYNTHETIC_CLIENTS, ids=lambda s: s.name)
def test_employee_identity_is_stable_across_years(spec, datasets):
    """Someone employed in consecutive years keeps their id.

    Without this, growth reads as total churn: every year would look like a
    brand-new workforce and net-new would be meaningless.
    """
    dataset = datasets[spec.name]
    by_year: dict[int, set[int]] = defaultdict(set)
    for p in dataset.payroll:
        by_year[p.pay_period_end.year].add(p.employee_id)

    years = sorted(by_year)
    carried = [
        len(by_year[a] & by_year[b]) / max(1, len(by_year[a]))
        for a, b in zip(years, years[1:])
    ]
    assert min(carried) > 0.5, (
        f"{spec.name}: only {min(carried):.0%} of employees carry into the next "
        f"year — identity is not stable"
    )


@pytest.mark.parametrize("spec", SYNTHETIC_CLIENTS, ids=lambda s: s.name)
def test_generation_is_deterministic(spec):
    """Same seed, same bytes — a pinned snapshot hash has to stay meaningful."""
    first = build_synthetic_dataset(spec)
    second = build_synthetic_dataset(spec)
    assert len(first.payroll) == len(second.payroll)
    assert [
        (p.employee_id, p.pay_period_start, p.hours, p.wages) for p in first.payroll[:500]
    ] == [
        (p.employee_id, p.pay_period_start, p.hours, p.wages) for p in second.payroll[:500]
    ]


def test_trajectory_must_cover_the_window():
    """A spec that does not describe every year is a spec with a silent gap."""
    from data.source.synth import SyntheticClientSpec

    with pytest.raises(ValueError, match="expected 6"):
        SyntheticClientSpec(
            account_id=9999, name="Too Short", states=("GA",), base_employees=10,
            worksites=1, fiscal_begin=date(2020, 1, 1), fiscal_end=date(2020, 12, 31),
            pay_frequency_id=3, period_days=14, trajectory=(1.0, 1.1), narrative="",
        )

    with pytest.raises(ValueError, match="must be 1.0"):
        SyntheticClientSpec(
            account_id=9999, name="Bad Base", states=("GA",), base_employees=10,
            worksites=1, fiscal_begin=date(2020, 1, 1), fiscal_end=date(2020, 12, 31),
            pay_frequency_id=3, period_days=14,
            trajectory=(0.9, 1.0, 1.1, 1.2, 1.3, 1.4), narrative="",
        )


# ------------------------------------------------------------- the stories


def test_cascade_grows_and_qualifies_every_year(datasets):
    spec = _BY_NAME["Cascade Retail Partners"]
    result = _tranches(spec, datasets[spec.name])

    assert all(y.qualified for y in result.years), "the clean case must qualify throughout"
    assert result.years[-1].average_headcount > result.base_average_headcount * 1.3
    assert len(result.tranche_events) >= 3, "steady growth should open several tranches"


# ------------------------------------------------- the "how am I doing" story


def _ga_unit_averages(spec, dataset, tax_year):
    index = spec.generated_years.index(tax_year)
    begin = _shift_years(spec.fiscal_begin, index)
    end = _shift_years(spec.fiscal_end, index)
    rows = [
        r for r in source_to_bcs_rows(dataset)
        if r["Work_State"] == "GA" and begin.isoformat() <= r["Pay_Date"] <= end.isoformat()
    ]
    result = run_pay_period_method(
        rows, tax_year=tax_year, analysis_start_month=begin,
        pack=load_pack_one_zero("GA", tax_year=tax_year), fiscal_window=(begin, end),
    )
    return {s["Worksite_ID"]: s for s in result.summary}


def test_ga007_falls_short_in_ty2025(datasets):
    """WI-11. GA-007 gives back its growth from June TY2025, so the location
    grid paints it below minimum while the client still qualifies."""
    spec = _BY_NAME["Cascade Retail Partners"]
    dataset = datasets[spec.name]
    base = _ga_unit_averages(spec, dataset, BASE_TAX_YEAR)
    ty2025 = _ga_unit_averages(spec, dataset, 2025)
    site = "GA_GA-007"
    net_new = ty2025[site]["average_headcount"] - base[site]["average_headcount"]
    assert net_new < 1.0, f"{site} should be about two jobs short of the minimum"
    months = ty2025[site]["month_totals"]
    # Present through May, gone from June: the loss sits in months that are
    # closed by the 31 August checkpoint the progress view projects from.
    assert months[4] > months[5], f"{site} should lose jobs in June, not before"
    assert months[4] >= months[0] - 1, f"{site} should not lose jobs before June"
    # A month with no counted job reads as a partial year, not a shortfall.
    assert min(months) > 0, f"{site} emptied out; the grid would call it partial"


def test_ga016_opens_in_ty2023_qualifies_then_dips_in_ty2026(datasets):
    """30 Sep. GA-016 is a newer store: TY2023 is its base, TY2024 and TY2025
    clear the two-job minimum against it, and the open TY2026 is below so far —
    the current year only, not a previous AND a current one."""
    spec = _BY_NAME["Cascade Retail Partners"]
    dataset = datasets[spec.name]
    site = "GA_GA-016"
    location_id = next(l.location_id for l in dataset.locations if l.client_location_id == "GA-016")
    opened = min(p.pay_period_start for p in dataset.payroll if p.location_id == location_id)
    assert opened == date(2023, 1, 1), "nothing is paid at GA-016 before it opens"

    base = _ga_unit_averages(spec, dataset, 2023)[site]
    assert min(base["month_totals"]) > 0, "the base year must be complete to be the base"
    for year in (2024, 2025):
        net_new = _ga_unit_averages(spec, dataset, year)[site]["average_headcount"] - base["average_headcount"]
        assert net_new >= 2.0, f"GA-016 should clear the two-job minimum in TY{year}"

    # The open year, read on its closed months as the grid reads it.
    months = _ga_unit_averages(spec, dataset, 2026)[site]["month_totals"]
    closed = [m for m in months if m > 0]
    assert len(closed) >= 6 and min(closed) > 0, "GA-016 must not empty out"
    to_date = sum(closed) / len(closed)
    short = base["average_headcount"] + 2.0 - to_date
    assert 0 < short < 1.5, f"GA-016 should be just under the line so far, not {short:.2f} short"


def test_story_events_draw_nothing_from_the_seed():
    """The stories open a site, add named hires and remove named leavers; they
    must not regenerate anybody else."""
    from dataclasses import replace

    from data.source.synth import _STORY_EMPLOYEE_OFFSET

    spec = _BY_NAME["Cascade Retail Partners"]
    shaped_ds = build_synthetic_dataset(spec)
    shaped = shaped_ds.payroll
    plain = build_synthetic_dataset(replace(spec, departures=(), openings=(), hirings=())).payroll
    key = lambda p: (p.payroll_id, p.employee_id, p.pay_period_start, p.hours, p.wages)
    story_floor = spec.account_id * 100_000 + _STORY_EMPLOYEE_OFFSET
    plain_keys = {key(p) for p in plain}
    shaped_keys = {key(p) for p in shaped}

    added = [p for p in shaped if key(p) not in plain_keys]
    assert added and all(p.employee_id >= story_floor for p in added), (
        "shaping altered a generated row rather than only adding the named hires"
    )
    removed = [p for p in plain if key(p) not in shaped_keys]
    assert removed, "the stories removed nothing"
    by_site = {l.location_id: l.client_location_id for l in shaped_ds.locations}
    assert {by_site[p.location_id] for p in removed} == {"GA-016", "GA-007"}, (
        "the stories leaked beyond the two named sites"
    )
    assert {by_site[p.location_id] for p in added} == {"GA-016"}


def test_northwind_falls_below_base_then_backfills(datasets):
    """The high-water mark case: a recovery is not all new jobs."""
    spec = _BY_NAME["Northwind Care Systems"]
    result = _tranches(spec, datasets[spec.name])

    non_qualifying = [y for y in result.years if not y.qualified]
    assert non_qualifying, "Northwind must spend years below its frozen base"

    assert any(y.backfilled for y in result.years), (
        "Northwind must re-qualify after a non-qualifying year"
    )

    # The point of the frozen base: the final year's claim is measured against
    # 2020, not against the trough it climbed out of.
    final = result.years[-1]
    trough = min(y.average_headcount for y in result.years)
    assert final.net_new < final.average_headcount - trough + 1, (
        "the rebound is being treated as fresh job creation"
    )


def test_ironbridge_spends_a_year_under_the_statutory_minimum(datasets):
    """Net-new above zero but below the threshold — real growth, no credit.

    This is the retroactive pitch in one row: nothing was claimable then, and
    something is claimable now, and only a multi-year view shows the difference.
    """
    spec = _BY_NAME["Ironbridge Logistics"]
    result = _tranches(spec, datasets[spec.name])

    under = [y for y in result.years if 0 < y.net_new < y.threshold]
    assert under, (
        "Ironbridge must have a year with growth that falls short of the "
        f"two-job minimum; got {[(y.year, round(y.net_new, 1)) for y in result.years]}"
    )
    assert all(y.eligible_jobs == 0 for y in under)
    assert all(y.annual_credit_usd == 0 for y in under)

    assert result.years[-1].qualified, "and it must clear the minimum later"


def test_halloway_stops_qualifying_while_its_tranches_run_on(datasets):
    """The exposure case: installments outlive the jobs behind them."""
    spec = _BY_NAME["Halloway Foods"]
    result = _tranches(spec, datasets[spec.name])

    assert result.years[0].qualified, "Halloway grows before it shrinks"

    lapsed = [y for y in result.years if not y.qualified]
    assert lapsed, "Halloway must fall back below its frozen base"
    assert lapsed[-1].year == result.years[-1].year, "and stay there"

    # The high-water mark records the peak even though the jobs are gone. That
    # gap is the exposure.
    assert result.final_high_water_mark > lapsed[-1].average_headcount * 1.2

    # At least one tranche created before the decline is still inside its
    # five-year window in the final year.
    final_year = result.years[-1].year
    assert any(
        e.creation_year + result.tranche_years > final_year for e in result.tranche_events
    ), "no tranche is still running, so there is no exposure to show"


# ------------------------------------------------------------ the guardrail


@pytest.mark.parametrize("spec", SYNTHETIC_CLIENTS, ids=lambda s: s.name)
def test_eligible_share_does_not_collapse(spec, datasets):
    """Georgia's floor rose 27% across this window. Wages have to keep up.

    If this fails, the synthetic wage band needs re-tuning against the current
    statute — do NOT adjust the statute. A collapse here would otherwise reach
    the demo as an all-but-empty eligibility screen with no error anywhere.
    """
    dataset = datasets[spec.name]
    rows = [r for r in source_to_bcs_rows(dataset) if r["Work_State"] == "GA"]
    assert rows, f"{spec.name} has no GA rows"

    for index, tax_year in enumerate(spec.tax_years):
        begin = _shift_years(spec.fiscal_begin, index)
        end = _shift_years(spec.fiscal_end, index)
        window = [r for r in rows if begin.isoformat() <= r["Pay_Date"] <= end.isoformat()]
        if not window:
            continue

        totals: dict[str, list] = defaultdict(lambda: [0.0, 0.0, set()])
        for row in window:
            entry = totals[row["Employee_ID"]]
            entry[0] += float(row["Hours_Worked"] or 0)
            entry[1] += float(row["Gross_Wages"] or 0)
            entry[2].add((row["Pay_Period_Start"], row["Pay_Period_End"]))

        floors = resolve_statutory_floors("GA_JTC", tax_year)
        eligible = 0
        for hours, wages, periods in totals.values():
            weeks = sum(
                (date.fromisoformat(pe) - date.fromisoformat(ps)).days + 1
                for ps, pe in periods
            ) / 7.0
            if weeks > 0 and hours / weeks >= floors.min_weekly_hours and wages / weeks >= floors.min_weekly_wages:
                eligible += 1

        share = eligible / len(totals)
        assert share >= 0.35, (
            f"{spec.name} TY{tax_year}: only {share:.0%} eligible against a "
            f"${floors.min_weekly_wages:.0f} floor — the demo would look empty"
        )
