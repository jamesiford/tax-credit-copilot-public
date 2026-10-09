"""Tests for the One/Zero Base Calculation engine.

Validates against the canonical fixtures from the partner's prompt docs
in `stakeholder-docs/`:

  - `One Zero Pay Periods.docx` -> 7-step Pay Period Method
  - `One Zero Min Max.docx`     -> 6-step Min Max Method (incl. EE 61200202
                                    multi-unit example, mirrored on E00200)
  - `GA JTC One Zero Methodology Overview.xlsx` -> visual examples

Run from `backend/`:
    pytest tests/test_onezero.py -v
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from domain.calculation.onezero import (
    OneZeroMethodology,
    OneZeroPack,
    first_measurable_month,
    preprocess,
    reconcile_methods,
    run_min_max_method,
    run_pay_period_method,
    unreachable_months,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ga_pack() -> OneZeroPack:
    """GA Jobs Tax Credit eligibility pack (from `ga_jtc.json`).

    Floors mirror the partner's prompt docs verbatim: >=35 hrs/wk avg AND >=$680/wk avg."""
    return OneZeroPack(
        min_weekly_hours=35.0,
        min_weekly_wages=680.0,
        wage_basis="regular",
        geographic_granularity="unit",
        pt_aggregation=False,
        headcount_unit_field="Worksite_ID",
        citation="OCGA \u00a7 48-7-40",
    )


# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------


def test_preprocess_filters_tax_year(pay_period_rows, ga_pack):
    """Step 0: rows whose PaycheckDate falls in a different tax year are dropped."""
    rows_2025 = preprocess(pay_period_rows, tax_year=2025)
    assert all(r["Pay_Date"].startswith("2025") or r["Pay_Date"].startswith("2026-01") for r in rows_2025)
    # Sanity: at least 5,000 rows survive (we generate ~5,700 for 2025).
    assert len(rows_2025) >= 4500
    rows_2024 = preprocess(pay_period_rows, tax_year=2024)
    assert all(r["Pay_Date"].startswith("2024") or r["Pay_Date"].startswith("2025-01") for r in rows_2024)


def test_preprocess_keeps_zero_hour_rows_by_default():
    """BA-05 — a zero-hour wage row is a real payroll fact and stays.

    The older behaviour dropped these as bonus runs. The partner's method keeps the
    wages in the numerator, so the certified default retains the row; a pack
    can opt back out via `count_zero_hour_periods`.
    """
    rows = [
        {"Tax_Year": 2025, "Employee_ID": "E001", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-07",
         "Pay_Date": "2025-01-12", "Hours_Worked": 40.0, "Gross_Wages": 1000.0,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular"},
        {"Tax_Year": 2025, "Employee_ID": "E001", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-08", "Pay_Period_End": "2025-01-14",
         "Pay_Date": "2025-01-19", "Hours_Worked": 0.0, "Gross_Wages": 500.0,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Bonus"},
    ]
    out = preprocess(rows, tax_year=2025)
    assert len(out) == 2
    assert sum(r["Gross_Wages"] for r in out) == 1500.0

    dropped = preprocess(
        rows,
        tax_year=2025,
        methodology=OneZeroMethodology(count_zero_hour_periods=False),
    )
    assert len(dropped) == 1
    assert dropped[0]["Pay_Code"] == "Regular"


def test_preprocess_collapses_duplicates():
    """Identical (EE, Unit, PPS, PPE) rows get summed."""
    rows = [
        {"Tax_Year": 2025, "Employee_ID": "E001", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-07",
         "Pay_Date": "2025-01-12", "Hours_Worked": 40.0, "Gross_Wages": 1000.0,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular"},
        {"Tax_Year": 2025, "Employee_ID": "E001", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-07",
         "Pay_Date": "2025-01-12", "Hours_Worked": 4.0, "Gross_Wages": 150.0,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Overtime"},
    ]
    out = preprocess(rows, tax_year=2025)
    assert len(out) == 1
    assert out[0]["Hours_Worked"] == 44.0
    assert out[0]["Gross_Wages"] == 1150.0


# ---------------------------------------------------------------------------
# Pay Period Method
# ---------------------------------------------------------------------------


def test_pay_period_method_runs_end_to_end(pay_period_rows, ga_pack):
    """Smoke test: PP method produces a populated result on the GA subset."""
    ga_rows = [r for r in pay_period_rows if r["Worksite_ID"].startswith("GA_")]
    result = run_pay_period_method(
        ga_rows,
        tax_year=2025,
        analysis_start_month=date(2025, 1, 1),
        pack=ga_pack,
    )
    assert result.method == "pay_period"
    assert len(result.months) == 12
    assert result.months[0] == date(2025, 1, 31)
    assert result.months[11] == date(2025, 12, 31)
    # GA should have a non-trivial eligible-employee count.
    assert len(result.eligible_employees) > 50
    # Annual average headcount should be a meaningful number.
    assert result.annual_average > 50


def test_pay_period_eligibility_floor_excludes_low_hours(ga_pack):
    """A 20-hour-per-week part-timer below the 35-hr/wk floor must be excluded."""
    rows = [
        # Eligible: 40 hrs / week, $800 / week
        {"Tax_Year": 2025, "Employee_ID": "FULL", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-07",
         "Pay_Date": "2025-01-12", "Hours_Worked": 40, "Gross_Wages": 800,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular"},
        {"Tax_Year": 2025, "Employee_ID": "FULL", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-08", "Pay_Period_End": "2025-01-14",
         "Pay_Date": "2025-01-19", "Hours_Worked": 40, "Gross_Wages": 800,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular"},
        # Ineligible: 20 hrs / week below 35-hr floor
        {"Tax_Year": 2025, "Employee_ID": "PART", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-07",
         "Pay_Date": "2025-01-12", "Hours_Worked": 20, "Gross_Wages": 700,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular"},
        {"Tax_Year": 2025, "Employee_ID": "PART", "Worksite_ID": "U1",
         "Pay_Period_Start": "2025-01-08", "Pay_Period_End": "2025-01-14",
         "Pay_Date": "2025-01-19", "Hours_Worked": 20, "Gross_Wages": 700,
         "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular"},
    ]
    result = run_pay_period_method(
        rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack
    )
    eligible_ids = {e["Employee_ID"] for e in result.eligible_employees}
    assert "FULL" in eligible_ids
    assert "PART" not in eligible_ids


# ---------------------------------------------------------------------------
# Min Max Method
# ---------------------------------------------------------------------------


def test_min_max_method_runs_end_to_end(pay_period_rows, ga_pack):
    """Smoke test: Min Max method produces a populated result."""
    ga_rows = [r for r in pay_period_rows if r["Worksite_ID"].startswith("GA_")]
    result = run_min_max_method(
        ga_rows,
        tax_year=2025,
        analysis_start_month=date(2025, 1, 1),
        pack=ga_pack,
    )
    assert result.method == "min_max"
    assert len(result.eligible_employees) > 50
    assert result.annual_average > 50


def test_min_max_canonical_fixture_E00200(pay_period_rows, ga_pack):
    """E00200 is our analog of the partner's EE 61200202 worked example.

    In the generator, E00200 rotates across:
        GA_MAC_OPS  Jan 6 -> Feb 16 2025
        GA_SAV_DC   Feb 17 -> Dec 7 2025
        GA_ATL_HQ   Dec 15 -> Dec 21 2025 (Month-12 special rule applies)

    Per the partner's spec, the Min Max matrix for this employee should show:
        - GA_MAC_OPS: 1 in Jan, 0 in Feb-Dec
        - GA_SAV_DC:  0 in Jan, 1 in Feb-Nov, 0 in Dec
        - GA_ATL_HQ:  0 in Jan-Nov, 1 in Dec (via Month-12 special rule
                       because LastPPE Dec 21 has day > 15)

    But after the no-double-count tie-breaker, the LAST unit chronologically
    wins any month where multiple units could claim a 1.
    """
    result = run_min_max_method(
        pay_period_rows,
        tax_year=2025,
        analysis_start_month=date(2025, 1, 1),
        pack=ga_pack,
    )
    e00200_rows = [r for r in result.employee_unit_matrix if r["Employee_ID"] == "E00200"]
    assert len(e00200_rows) == 3, f"Expected 3 unit rows for E00200, got {len(e00200_rows)}"

    by_unit = {r["Worksite_ID"]: r["months"] for r in e00200_rows}
    assert set(by_unit.keys()) == {"GA_MAC_OPS", "GA_SAV_DC", "GA_ATL_HQ"}

    # MAC: covers Jan only
    assert by_unit["GA_MAC_OPS"][0] == 1   # Jan
    assert sum(by_unit["GA_MAC_OPS"][1:]) == 0  # Feb-Dec: no months

    # SAV: covers Feb-Nov (10 months)
    assert by_unit["GA_SAV_DC"][0] == 0
    assert sum(by_unit["GA_SAV_DC"][1:11]) == 10  # Feb-Nov inclusive
    assert by_unit["GA_SAV_DC"][11] == 0          # Dec NOT (range ends Dec 7)

    # ATL: only Dec, via Month-12 special rule
    assert sum(by_unit["GA_ATL_HQ"][:11]) == 0
    assert by_unit["GA_ATL_HQ"][11] == 1


def test_dedupe_prevents_double_count(ga_pack):
    """No employee may show a 1 in the same month for more than one unit."""
    rows = []
    # Employee at Unit 1 Jan 1 -> Feb 28
    for d_start in (date(2025, 1, 1), date(2025, 1, 8), date(2025, 1, 15), date(2025, 1, 22),
                    date(2025, 1, 29), date(2025, 2, 5), date(2025, 2, 12), date(2025, 2, 19), date(2025, 2, 26)):
        rows.append({
            "Tax_Year": 2025, "Employee_ID": "DUP", "Worksite_ID": "U1",
            "Pay_Period_Start": d_start.isoformat(),
            "Pay_Period_End": (date(d_start.year, d_start.month, min(d_start.day + 6, 28))).isoformat(),
            "Pay_Date": (date(d_start.year, d_start.month, min(d_start.day + 6, 28))).isoformat(),
            "Hours_Worked": 40, "Gross_Wages": 800,
            "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular",
        })
    # Same employee also at Unit 2 spanning Jan-Feb (causes overlap)
    rows.append({
        "Tax_Year": 2025, "Employee_ID": "DUP", "Worksite_ID": "U2",
        "Pay_Period_Start": "2025-01-15", "Pay_Period_End": "2025-02-15",
        "Pay_Date": "2025-02-20", "Hours_Worked": 80, "Gross_Wages": 1600,
        "Job_Title": "x", "Entity_FEIN": "x", "Pay_Code": "Regular",
    })
    result = run_min_max_method(
        rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack
    )
    # After dedup, sum across both units in the summary equals at-most-one per month
    by_unit_summary = {r["Worksite_ID"]: r["month_totals"] for r in result.summary}
    for m in range(12):
        total = sum(by_unit_summary.get(u, [0] * 12)[m] for u in by_unit_summary)
        assert total <= 1, f"Month {m+1} has total {total} after dedup; expected <=1"


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def test_reconciliation_runs(pay_period_rows, ga_pack):
    """Both methods + reconcile should produce per-unit diff data."""
    ga_rows = [r for r in pay_period_rows if r["Worksite_ID"].startswith("GA_")]
    pp = run_pay_period_method(
        ga_rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack
    )
    mm = run_min_max_method(
        ga_rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack
    )
    report = reconcile_methods(pp, mm)
    assert len(report.units) > 0
    assert all("Worksite_ID" in u for u in report.units)
    # Donut hole rule: PP weeks should never exceed MM weeks (impossible per
    # the source doc). The generator produces clean data so this should be
    # empty; the test guards against engine regressions that would invent weeks.
    assert len(report.employee_weeks_donut_hole) == 0, (
        f"Donut hole violations: {report.employee_weeks_donut_hole[:3]}"
    )
    # [Phase C] Min Max (best scenario) >= Pay Period (1/0) must hold on the
    # clean synthetic data — no eligibility-set divergence.
    assert report.invariant_holds is True
    assert report.invariant_violations == []


def _gapped_biweekly_rows(ee: str, unit: str, fein: str = "22-2222222") -> list[dict]:
    """Ten biweekly pay periods, each straddling a distinct month-end (Jan..Oct)
    with a gap between them. Under the Pay Period method the employee has ~20
    weeks worked (10 major biweekly periods) -> high weekly average -> eligible;
    under Min Max the weeks basis is the full Jan->Nov calendar span -> low
    weekly average -> INELIGIBLE. This is the mid-year-gap case that makes Min
    Max fall below Pay Period."""
    rows: list[dict] = []
    for m in range(1, 11):  # Jan..Oct
        last = date(2025, m + 1, 1) - timedelta(days=1)
        pps = last - timedelta(days=11)
        ppe = last + timedelta(days=2)
        rows.append({
            "Tax_Year": 2025, "Employee_ID": ee, "Worksite_ID": unit,
            "Pay_Period_Start": pps.isoformat(), "Pay_Period_End": ppe.isoformat(),
            "Pay_Date": (ppe + timedelta(days=5)).isoformat(),
            "Hours_Worked": 80.0, "Gross_Wages": 2000.0,
            "Job_Title": "x", "Entity_FEIN": fein, "Pay_Code": "Regular",
        })
    return rows


def test_invariant_violation_flagged_on_gapped_employee(ga_pack):
    """[Phase C] A mid-year-gap employee eligible under Pay Period but dropped
    by Min Max's full-span weeks basis makes Min Max < Pay Period. The
    reconciliation must FLAG it (invariant_holds False), never silently accept."""
    rows = _gapped_biweekly_rows("EGAP", "GA_TEST_UNIT")
    pp = run_pay_period_method(
        rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack
    )
    mm = run_min_max_method(
        rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack
    )
    # Pay Period counts the employee; Min Max drops them.
    assert pp.annual_average > 0
    assert mm.annual_average < pp.annual_average
    report = reconcile_methods(pp, mm)
    assert report.invariant_holds is False
    assert any(v["Worksite_ID"] == "GA_TEST_UNIT" for v in report.invariant_violations)


# ---------------------------------------------------------------------------
# [H1] CALC-03 — per-year thresholds + per-employee audit flags
# ---------------------------------------------------------------------------


def _full_year_rows(ee: str, unit: str, hours: float, wages: float, fein: str = "11-1111111") -> list[dict]:
    """52 weekly pay periods of constant hours/wages for one employee/unit."""
    rows = []
    start = date(2025, 1, 1)
    for wk in range(52):
        pps = start + timedelta(days=7 * wk)
        ppe = pps + timedelta(days=6)
        rows.append({
            "Tax_Year": 2025, "Employee_ID": ee, "Worksite_ID": unit,
            "Pay_Period_Start": pps.isoformat(), "Pay_Period_End": ppe.isoformat(),
            "Pay_Date": (ppe + timedelta(days=5)).isoformat(),
            "Hours_Worked": hours, "Gross_Wages": wages,
            "Job_Title": "x", "Entity_FEIN": fein, "Pay_Code": "Regular",
        })
    return rows


def test_h1_calc03_per_employee_audit_flags(ga_pack):
    """Eligible employees carry passed_hours / passed_wages / weight for audit."""
    rows = _full_year_rows("FULL", "GA_ATL_HQ", 40, 900)
    result = run_pay_period_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack)
    assert len(result.eligible_employees) == 1
    e = result.eligible_employees[0]
    assert e["passed_hours"] is True
    assert e["passed_wages"] is True
    assert e["weight"] == 1.0


def test_h1_calc03_fails_hours_floor(ga_pack):
    """An employee below the GA 35-hr floor (no PT band) is ineligible."""
    rows = _full_year_rows("LOW", "GA_ATL_HQ", 25, 900)  # 25 hrs < 35
    result = run_pay_period_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=ga_pack)
    assert len(result.eligible_employees) == 0


def _sc_pack() -> OneZeroPack:
    """[H2] SC pack: no wage test, 32-hr full-time, 20-32 hr part-time = 0.5."""
    return OneZeroPack(
        min_weekly_hours=32.0, min_weekly_wages=0.0, wage_basis="regular",
        geographic_granularity="county", pt_aggregation=False,
        headcount_unit_field="Worksite_ID", citation="S.C. Code § 12-6-3360",
        pt_band_hours=(20.0, 32.0), pt_weight=0.5,
    )


def test_h2_calc03_sc_part_timer_counts_half():
    """SC employee averaging 25 hrs/wk lands in the 20-32 PT band -> weight 0.5."""
    pack = _sc_pack()
    rows = _full_year_rows("PT", "SC_CHS_DC", 25, 600)
    result = run_pay_period_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=pack)
    assert len(result.eligible_employees) == 1
    assert result.eligible_employees[0]["weight"] == 0.5
    # Average headcount for that single PT employee across 12 months = 0.5.
    assert result.annual_average == 0.5


def test_h2_calc03_sc_full_timer_counts_one():
    """SC employee at 40 hrs/wk is full-time -> weight 1.0."""
    pack = _sc_pack()
    rows = _full_year_rows("FT", "SC_CHS_DC", 40, 900)
    result = run_pay_period_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=pack)
    assert result.eligible_employees[0]["weight"] == 1.0
    assert result.annual_average == 1.0


def test_h2_calc03_sc_below_band_ineligible():
    """SC employee at 15 hrs/wk is below the 20-hr PT band -> ineligible."""
    pack = _sc_pack()
    rows = _full_year_rows("MINI", "SC_CHS_DC", 15, 400)
    result = run_pay_period_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=pack)
    assert len(result.eligible_employees) == 0


def test_h1_calc03_year_resolution_from_pack():
    """load_pack_one_zero resolves GA 2025 historical-table floor ($680)."""
    from tools.credit_math import load_pack_one_zero
    flat = load_pack_one_zero("GA")
    y2025 = load_pack_one_zero("GA", tax_year=2025)
    assert flat.min_weekly_wages == 680.0
    assert y2025.min_weekly_wages == 680.0


def test_h2_sc_pack_loads_part_time_band():
    """SC pack exposes the 20-32 hr part-time band + 0.5 weight for 2025."""
    from tools.credit_math import load_pack_one_zero
    sc = load_pack_one_zero("SC", tax_year=2025)
    assert sc.min_weekly_hours == 32.0
    assert sc.min_weekly_wages == 0.0          # no wage test
    assert sc.pt_band_hours == (20.0, 32.0)
    assert sc.pt_weight == 0.5


# ---------------------------------------------------------------------------
# [H3] CALC-04 — configurable measuring date
# ---------------------------------------------------------------------------


def test_h3_calc04_measuring_date_shifts_coverage():
    """A mid-month measuring date changes which employees count that month.

    An employee whose pay-period range ends on the 10th covers a '5th'
    measuring date but NOT the last-day default.
    """
    base = dict(
        min_weekly_hours=35.0, min_weekly_wages=680.0, wage_basis="regular",
        geographic_granularity="unit", pt_aggregation=False,
        headcount_unit_field="Worksite_ID", citation="OCGA § 48-7-40",
    )
    pack_last = OneZeroPack(**base, measuring_date="last_day")
    pack_fifth = OneZeroPack(**base, measuring_date="5")
    # One employee, single unit, range Jan 1 - Jan 10 only (then gone).
    rows = []
    for pps in (date(2025, 1, 1), date(2025, 1, 8)):
        ppe = min(pps + timedelta(days=6), date(2025, 1, 10))
        rows.append({
            "Tax_Year": 2025, "Employee_ID": "EDGE", "Worksite_ID": "GA_X",
            "Pay_Period_Start": pps.isoformat(), "Pay_Period_End": ppe.isoformat(),
            "Pay_Date": (ppe + timedelta(days=3)).isoformat(),
            "Hours_Worked": 40, "Gross_Wages": 900,
            "Job_Title": "x", "Entity_FEIN": "11-1", "Pay_Code": "Regular",
        })
    mm_last = run_min_max_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=pack_last)
    mm_fifth = run_min_max_method(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=pack_fifth)
    jan_last = mm_last.summary[0]["month_totals"][0] if mm_last.summary else 0
    jan_fifth = mm_fifth.summary[0]["month_totals"][0] if mm_fifth.summary else 0
    # Range ends Jan 10: covers the 5th but not Jan 31.
    assert jan_fifth == 1
    assert jan_last == 0


# ---------------------------------------------------------------------------
# [H4] CALC-05 — fiscal-year bucketing by pay date
# ---------------------------------------------------------------------------


def test_h4_calc05_fiscal_year_of_calendar():
    """Calendar year (fy_end_month=12) returns the pay date's calendar year."""
    from domain.calculation.onezero import fiscal_year_of
    assert fiscal_year_of(date(2025, 4, 15), 12) == 2025
    assert fiscal_year_of(date(2025, 12, 31), 12) == 2025


def test_h4_calc05_fiscal_year_of_march_end():
    """March year-end: April 2024 .. March 2025 all belong to FY2025."""
    from domain.calculation.onezero import fiscal_year_of
    assert fiscal_year_of(date(2024, 4, 1), 3) == 2025   # first day of FY2025
    assert fiscal_year_of(date(2024, 12, 31), 3) == 2025
    assert fiscal_year_of(date(2025, 3, 31), 3) == 2025  # last day of FY2025
    assert fiscal_year_of(date(2025, 4, 1), 3) == 2026   # rolls to FY2026


def test_h4_calc05_fiscal_window_start():
    """Window start is Jan 1 for calendar, Apr 1 of prior year for March-end."""
    from domain.calculation.onezero import fiscal_window_start
    assert fiscal_window_start(2025, 12) == date(2025, 1, 1)
    assert fiscal_window_start(2025, 3) == date(2024, 4, 1)


# ---------------------------------------------------------------------------
# The stub month at the head of a mid-month fiscal year
# ---------------------------------------------------------------------------


def _weekly_rows(first_start: date, weeks: int) -> list[dict]:
    return [
        {
            "Tax_Year": 2023, "Employee_ID": "E1", "Worksite_ID": "GA_X",
            "Entity_FEIN": "11-1111111", "Pay_Code": "Regular",
            "Pay_Period_Start": (first_start + timedelta(days=7 * w)).isoformat(),
            "Pay_Period_End": (first_start + timedelta(days=7 * w + 6)).isoformat(),
            "Pay_Date": (first_start + timedelta(days=7 * w + 9)).isoformat(),
            "Hours_Worked": 40.0, "Gross_Wages": 1000.0,
        }
        for w in range(weeks)
    ]


def test_a_year_opening_on_the_first_starts_measuring_immediately():
    rows = _weekly_rows(date(2023, 1, 2), 54)
    assert first_measurable_month(rows, (date(2023, 1, 1), date(2023, 12, 31))) == date(2023, 1, 1)


def test_a_stub_head_month_no_pay_period_reaches_is_skipped():
    """The reference client's year opens 2023-07-28; its first period starts 08-01.

    Nothing spans 2023-07-31, so starting there burns Month 1 on a date no
    payroll can reach AND pushes the window's real final month off the end.
    """
    rows = _weekly_rows(date(2023, 8, 1), 52)
    assert first_measurable_month(rows, (date(2023, 7, 28), date(2024, 8, 2))) == date(2023, 8, 1)


def test_a_mid_month_open_still_counts_the_month_when_a_period_spans_it():
    """Skipping is driven by the payroll, not by the day of the month."""
    rows = _weekly_rows(date(2024, 2, 12), 52)
    assert first_measurable_month(rows, (date(2024, 2, 15), date(2025, 2, 14))) == date(2024, 2, 1)


def test_payroll_that_reaches_no_month_end_falls_back_to_the_window():
    rows = _weekly_rows(date(2023, 8, 1), 1)
    window = (date(2023, 7, 28), date(2023, 8, 10))
    assert first_measurable_month(rows, window) == date(2023, 7, 28)


def test_a_month_no_pay_period_reaches_is_named():
    """Its zero is a fact about the pay calendar, not about headcount."""
    rows = _weekly_rows(date(2023, 8, 1), 52)
    months = [date(2023, 7, 31)] + [date(2023, 8, 31), date(2023, 9, 30)]

    assert unreachable_months(rows, months) == [0]


def test_a_fully_covered_year_names_nothing():
    rows = _weekly_rows(date(2023, 1, 2), 54)
    months = [date(2023, 1, 31), date(2023, 2, 28), date(2023, 3, 31)]

    assert unreachable_months(rows, months) == []


def test_the_reference_shape_flags_its_own_last_month():
    """Nothing spans 2024-07-31; Month 12 survives only via the special rule."""
    rows = _weekly_rows(date(2023, 8, 1), 51)  # last period ends 2024-07-20
    months = [date(2024, 6, 30), date(2024, 7, 31)]

    assert unreachable_months(rows, months) == [1]


def test_h4_calc05_pay_date_buckets_into_fiscal_year(ga_pack):
    """A period worked + paid in April 2024 lands in FY2025 under a March year-end.

    Same row set yields zero FY2024 employees but one FY2025 employee when the
    fiscal year-end is March.
    """
    rows = []
    # Weekly periods April 2024 -> March 2025 (full March fiscal year).
    start = date(2024, 4, 1)
    for wk in range(52):
        pps = start + timedelta(days=7 * wk)
        ppe = pps + timedelta(days=6)
        rows.append({
            "Tax_Year": 2025, "Employee_ID": "FY", "Worksite_ID": "GA_X",
            "Pay_Period_Start": pps.isoformat(), "Pay_Period_End": ppe.isoformat(),
            "Pay_Date": (ppe + timedelta(days=3)).isoformat(),
            "Hours_Worked": 40, "Gross_Wages": 900,
            "Job_Title": "x", "Entity_FEIN": "11-1", "Pay_Code": "Regular",
        })
    fy = run_pay_period_method(
        rows, tax_year=2025, analysis_start_month=date(2024, 4, 1),
        pack=ga_pack, fiscal_year_end_month=3,
    )
    assert len(fy.eligible_employees) == 1
    # Under a calendar year the same rows split across 2024/2025 -> fewer weeks.
    cal = run_pay_period_method(
        rows, tax_year=2025, analysis_start_month=date(2025, 1, 1),
        pack=ga_pack, fiscal_year_end_month=12,
    )
    # Calendar FY2025 only sees Jan-Mar 2025 pay dates (~13 weeks) for this EE.
    assert fy.eligible_employees[0]["weeks_worked"] > cal.eligible_employees[0]["weeks_worked"]


