"""Running both methods and surfacing where they disagree.

Min Max and Pay Period measure the same population with different denominators.
Where they disagree about one employee, that employee sits near a boundary - and
near-boundary cases are where a filed number is most likely to be challenged.

Comparison, not calculation. This calls the two engines; neither calls it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .onezero import (
    OneZeroPack,
    OneZeroResult,
    fiscal_window_start,
    run_min_max_method,
    run_pay_period_method,
)


# ---------------------------------------------------------------------------
# Reconciliation (run both methods, surface divergence)
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationReport:
    """Side-by-side comparison of Pay Period vs Min Max outputs."""
    units: list[dict]                         # per-unit per-month diffs
    employee_weeks_donut_hole: list[dict]     # PP weeks > MM weeks (weeks-level data-quality signal)
    eligibility_disagreements: list[dict]     # employees eligible in one method, not the other
    invariant_violations: list[dict]          # [Phase C] units where PP avg > MM avg (MinMax must be >= 1/0)
    invariant_holds: bool                     # [Phase C] True when MinMax >= PayPeriod for every unit
    annual_average_pp: float
    annual_average_mm: float
    annual_average_diff: float


def reconcile_methods(pp: OneZeroResult, mm: OneZeroResult, *, donut_hole_tolerance_weeks: float = 1.5) -> ReconciliationReport:
    """Run both methods, surface divergence.

    PRIMARY invariant [Phase C] — the partner's rule: the **Min Max ("best scenario")
    average headcount must NEVER be less than the Pay Period (1/0) average.**
    Min Max builds its monthly One/Zero matrix as a CONTINUOUS envelope
    ([earliest PPS .. latest PPE] per employee-unit), so for the same eligible
    set it fills gaps the discrete Pay-Period matrix leaves as zeros -> Min Max
    total >= Pay Period total per unit-month. Any unit where Pay Period > Min Max
    is surfaced in `invariant_violations` (never silently accepted); it can only
    come from an eligibility-set divergence (an employee eligible under Pay
    Period but dropped by Min Max's full-span weeks basis, e.g. a mid-year gap).
    Ref: One Zero Min Max.docx Steps 5-6 vs One Zero Pay Periods.docx Step 6.

    SECONDARY signal — the weeks-level donut hole. `donut_hole_tolerance_weeks`
    (default 1.5): PP method counts discrete pay periods times cycle multiplier
    (integer), MM method counts calendar days/7 (fractional). On clean
    continuous data the two differ by up to ~1.14 weeks purely from end-of-week
    calendar edge effects (a semi-monthly employee gives PP=52 weeks but
    MM=50.86 weeks across a clean year). The default tolerance absorbs that
    natural variance; deltas above 1.5 weeks indicate a real data-quality issue
    (gaps in major periods, stale terminal pay periods, missing pay runs, etc).
    """
    # Per-unit-per-month diffs.
    pp_summary = {row["Worksite_ID"]: row["month_totals"] for row in pp.summary}
    mm_summary = {row["Worksite_ID"]: row["month_totals"] for row in mm.summary}
    units: list[dict] = []
    for unit in sorted(set(pp_summary.keys()) | set(mm_summary.keys())):
        pp_cols = pp_summary.get(unit, [0] * 12)
        mm_cols = mm_summary.get(unit, [0] * 12)
        diffs = [pp_cols[i] - mm_cols[i] for i in range(12)]
        units.append({
            "Worksite_ID": unit,
            "pay_period_totals": pp_cols,
            "min_max_totals": mm_cols,
            "month_diffs": diffs,
            "max_abs_diff": max(abs(d) for d in diffs),
            "pp_average": pp.average_headcount.get(unit, 0),
            "mm_average": mm.average_headcount.get(unit, 0),
        })

    # Donut hole: per-employee weeks_worked comparison. Only meaningful for
    # employees eligible under BOTH methods — eligibility disagreements are
    # tracked separately below and would otherwise produce false positives
    # (e.g., PP weeks=48 vs MM weeks=0 for an employee MM marked ineligible).
    pp_weeks = {r["Employee_ID"]: r["weeks_worked"] for r in pp.eligible_employees}
    mm_weeks = {r["Employee_ID"]: r["weeks_worked"] for r in mm.eligible_employees}
    both_eligible = set(pp_weeks.keys()) & set(mm_weeks.keys())
    donut: list[dict] = []
    for ee in sorted(both_eligible):
        pw = pp_weeks[ee]
        mw = mm_weeks[ee]
        if pw > mw + donut_hole_tolerance_weeks:
            donut.append({"Employee_ID": ee, "pp_weeks": pw, "mm_weeks": mw, "delta": round(pw - mw, 2)})

    # Eligibility disagreements.
    pp_eligible = {r["Employee_ID"] for r in pp.eligible_employees}
    mm_eligible = {r["Employee_ID"] for r in mm.eligible_employees}
    disagreements: list[dict] = []
    for ee in sorted(pp_eligible.symmetric_difference(mm_eligible)):
        disagreements.append({
            "Employee_ID": ee,
            "pay_period_eligible": ee in pp_eligible,
            "min_max_eligible": ee in mm_eligible,
        })

    # --- [Phase C] Min-Max >= Pay-Period invariant (the real "min/max should
    # never be less than 1/0" rule). A violation is a data-quality condition to
    # surface for human review, not silently accept.
    invariant_tolerance = 0.01  # absorb 2-dp rounding on the averages
    invariant_violations: list[dict] = []
    for u in units:
        if u["pp_average"] > u["mm_average"] + invariant_tolerance:
            offending_months = [
                i + 1 for i in range(12)
                if u["pay_period_totals"][i] > u["min_max_totals"][i] + invariant_tolerance
            ]
            invariant_violations.append({
                "Worksite_ID": u["Worksite_ID"],
                "pp_average": u["pp_average"],
                "mm_average": u["mm_average"],
                "delta": round(u["pp_average"] - u["mm_average"], 2),
                "offending_months": offending_months,
            })
    invariant_holds = not invariant_violations

    return ReconciliationReport(
        units=units,
        employee_weeks_donut_hole=donut,
        eligibility_disagreements=disagreements,
        invariant_violations=invariant_violations,
        invariant_holds=invariant_holds,
        annual_average_pp=pp.annual_average,
        annual_average_mm=mm.annual_average,
        annual_average_diff=round(pp.annual_average - mm.annual_average, 2),
    )
