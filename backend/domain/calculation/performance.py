"""The performance dashboard - are we tracking toward the credit this year?

A reporting view over results the engine produced. It projects and it colours;
it decides nothing statutory, and no part of the engine depends on it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .onezero import (
    OneZeroPack,
    _coerce_float,
    _parse_iso,
    apply_pay_code_policy,
    fiscal_window_start,
    preprocess,
    run_pay_period_method,
)


# ---------------------------------------------------------------------------
# Performance Dashboard (green/yellow/red headroom against the floors)
# ---------------------------------------------------------------------------


def run_performance_dashboard(
    rows: list[dict],
    *,
    tax_year: int,
    pack: OneZeroPack,
    yellow_margin: float = 0.05,
    per_job_usd: float = 0.0,
) -> dict[str, Any]:
    """Classify each employee as green / yellow / red against the One/Zero
    eligibility floors and compute the "additional hours / wages needed to
    qualify" + the incremental credit ROI.

    Status mapping:
      - green:  on track to meet wage/hour thresholds for maximum credit
                (>= 100% of both floors, with `yellow_margin` headroom)
      - yellow: close to qualifying - minor adjustments could push them over
                (within `yellow_margin` of either floor, either direction)
      - red:    unlikely to qualify based on current trajectory
                (>= `yellow_margin` BELOW either floor)

    Returns a dict with:
      summary - per-status counts + per-unit color split
      employees - per-employee classification + "additional hours/wages needed"
                  (anonymized: Employee_ID kept as-is since the prototype CSV
                  is already PII-scrubbed; production tokenizes via the
                  anonymization boundary)
    """
    rows = apply_pay_code_policy(rows, pack)  # [L5] CALC-11
    rows = preprocess(rows, tax_year=tax_year)

    # Aggregate per employee (same as PP/MM steps 1+2+3 but lighter).
    by_ee: dict[str, dict] = {}
    for r in rows:
        ee = r["Employee_ID"]
        slot = by_ee.setdefault(ee, {
            "Employee_ID": ee, "Worksite_ID": r["Worksite_ID"],
            "Job_Title": r.get("Job_Title", ""),
            "total_hours": 0.0, "total_wages": 0.0,
            "first_pps": _parse_iso(r["Pay_Period_Start"]),
            "last_ppe": _parse_iso(r["Pay_Period_End"]),
        })
        slot["total_hours"] += _coerce_float(r["Hours_Worked"])
        slot["total_wages"] += _coerce_float(r["Gross_Wages"])
        pps, ppe = _parse_iso(r["Pay_Period_Start"]), _parse_iso(r["Pay_Period_End"])
        if pps < slot["first_pps"]:
            slot["first_pps"] = pps
        if ppe > slot["last_ppe"]:
            slot["last_ppe"] = ppe

    employees: list[dict] = []
    for slot in by_ee.values():
        days = (slot["last_ppe"] - slot["first_pps"]).days
        weeks = max(days / 7.0, 0.01)
        avg_hours = slot["total_hours"] / weeks
        avg_wages = slot["total_wages"] / weeks
        hours_ratio = avg_hours / pack.min_weekly_hours if pack.min_weekly_hours > 0 else 1.0
        wages_ratio = avg_wages / pack.min_weekly_wages if pack.min_weekly_wages > 0 else 1.0
        worst_ratio = min(hours_ratio, wages_ratio)

        if worst_ratio >= 1.0 + yellow_margin:
            status = "green"
        elif worst_ratio >= 1.0 - yellow_margin:
            status = "yellow"
        else:
            status = "red"

        hours_gap = max(0.0, pack.min_weekly_hours - avg_hours)
        wages_gap = max(0.0, pack.min_weekly_wages - avg_wages)
        # [O3] UX-06 — dollarize the lever: converting a YELLOW employee to
        # eligible adds one net-new qualifying job (≈ per_job_usd/yr). Green are
        # already counted; red are unlikely to convert this year.
        credit_at_stake_usd = round(per_job_usd) if status == "yellow" else 0
        employees.append({
            "Employee_ID": slot["Employee_ID"],
            "Worksite_ID": slot["Worksite_ID"],
            "Job_Title": slot["Job_Title"],
            "weeks_worked": round(weeks, 2),
            "avg_weekly_hours": round(avg_hours, 2),
            "avg_weekly_wages": round(avg_wages, 2),
            "status": status,
            "hours_gap_per_week": round(hours_gap, 2),
            "wages_gap_per_week": round(wages_gap, 2),
            "annual_hours_to_qualify": round(hours_gap * 52, 1),
            "credit_at_stake_usd": credit_at_stake_usd,  # [O3]
        })
    employees.sort(key=lambda e: (e["Worksite_ID"], e["status"], e["Employee_ID"]))

    # Summary counts.
    by_status = {"green": 0, "yellow": 0, "red": 0}
    for e in employees:
        by_status[e["status"]] += 1

    # Per-unit color split.
    by_unit_status: dict[str, dict[str, int]] = defaultdict(lambda: {"green": 0, "yellow": 0, "red": 0, "total": 0})
    for e in employees:
        by_unit_status[e["Worksite_ID"]][e["status"]] += 1
        by_unit_status[e["Worksite_ID"]]["total"] += 1
    units_summary = [
        {
            "Worksite_ID": unit,
            "green": cols["green"],
            "yellow": cols["yellow"],
            "red": cols["red"],
            "total": cols["total"],
        }
        for unit, cols in sorted(by_unit_status.items())
    ]

    return {
        "tax_year": tax_year,
        "pack_citation": pack.citation,
        "min_weekly_hours": pack.min_weekly_hours,
        "min_weekly_wages": pack.min_weekly_wages,
        "yellow_margin": yellow_margin,
        "summary": by_status,
        "units": units_summary,
        "employees": employees,
        "employee_count": len(employees),
    }
