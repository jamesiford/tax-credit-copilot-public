"""Forward-looking views - are we on track, and what would change that.

Split out of `api/onezero.py`. Everything here PROJECTS: a run-rate forecast to
year end, month-by-month alerts, threshold triggers, and the performance
dashboard. None of it is a filed figure, and each states its method so an
estimate never reads like a calculated result.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from api._payperiods import iter_state_packs, require_pay_periods
from application.queries.get_in_year_progress import (
    GetInYearProgressQuery,
    ProgressNotAvailable,
)
from application.wiring import get_mediator

router = APIRouter(prefix="/api", tags=["forecast"])


@router.get("/progress/{tax_year}")
def in_year_progress(
    tax_year: int,
    state: str,
    as_of: str | None = None,
    account_id: int | None = None,
    within: float = 5.0,
) -> dict[str, Any]:
    """Are we on track this year, and who would move the needle.

    `as_of` defaults to 31 August — the checkpoint after the August payroll
    settles, with eight months of actuals to project from. The result is an
    **estimate**: a linear run-rate with no seasonality, measured over the
    months that have closed rather than over twelve.
    """
    parsed: date | None = None
    if as_of:
        try:
            parsed = date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="as_of must be an ISO date (YYYY-MM-DD)"
            ) from exc

    try:
        return get_mediator().send(
            GetInYearProgressQuery(
                tax_year=tax_year,
                state=state,
                as_of=parsed,
                account_id=account_id,
                proximity_band_hours=within,
            )
        )
    except ProgressNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/forecast/{tax_year}")
def forecast(
    tax_year: int,
    state: str | None = None,
    as_of: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """[N2] FCST-01 — "how am I doing" run-rate forecast toward the finish line.

    Projects each state's year-end One/Zero credit from year-to-date actuals
    (linear run-rate, no seasonality). `as_of` (ISO date) defaults to Aug 31 of
    the tax year so the trajectory has ~8 months of actuals to project from.
    """
    from tools.forecast import project_state_year_end
    from domain.calculation.onezero import fiscal_year_of
    from config import get_fiscal_year_end_month

    try:
        as_of_date = date.fromisoformat(as_of) if as_of else date(tax_year, 8, 31)
    except ValueError:
        raise HTTPException(status_code=422, detail="as_of must be an ISO date (YYYY-MM-DD)")

    fy_end_month = get_fiscal_year_end_month()
    all_rows = require_pay_periods(account_id=account_id)

    def _fy(row: dict[str, Any]) -> int:
        return fiscal_year_of(date.fromisoformat(str(row["Pay_Date"])[:10]), fy_end_month)

    rows = [r for r in all_rows if _fy(r) == tax_year]
    prior_rows = [r for r in all_rows if _fy(r) == tax_year - 1]

    results: list[dict[str, Any]] = []
    for st, _pack, _state_rows in iter_state_packs(rows, tax_year=tax_year, state=state):
        proj = project_state_year_end(
            st, tax_year, rows, prior_rows, as_of=as_of_date, fiscal_year_end_month=fy_end_month,
        )
        if proj is not None:
            results.append(proj)

    results.sort(key=lambda r: r["projected_annual_credit_usd"], reverse=True)
    return {
        "as_of": as_of_date.isoformat(),
        "tax_year": tax_year,
        "fiscal_year_end_month": fy_end_month,
        "estimated_credit_total_usd": sum(r["projected_annual_credit_usd"] for r in results),
        "state_count": len(results),
        "states": results,
    }


@router.get("/alerts/monthly/{tax_year}")
def monthly_alerts(
    tax_year: int,
    state: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """[J3] UX-03 — monthly credit-tracking alerts anchored on the measuring date.

    Classifies each unit on_track / at_risk / exceeding and, for borderline
    (yellow) employees, emits the SPECIFIC lever needed to clear the threshold.
    The lever numbers come straight from the engine, not hand-authored copy.
    """
    from domain.calculation.onezero import run_performance_dashboard

    rows = require_pay_periods(account_id=account_id)
    rows = [r for r in rows if r["Tax_Year"] == tax_year]

    unit_alerts: list[dict[str, Any]] = []
    employee_levers: list[dict[str, Any]] = []
    status_counts = {"on_track": 0, "at_risk": 0, "exceeding": 0}

    for st, pack, state_rows in iter_state_packs(rows, tax_year=tax_year, state=state):
        perf = run_performance_dashboard(state_rows, tax_year=tax_year, pack=pack)

        # Per-unit on_track / at_risk / exceeding classification.
        for u in perf["units"]:
            if u["yellow"] == 0 and u["red"] == 0:
                ustatus = "exceeding"
            elif u["yellow"] > 0:
                ustatus = "at_risk"
            else:
                ustatus = "on_track"
            status_counts[ustatus] += 1
            unit_alerts.append({
                "state": st,
                "Worksite_ID": u["Worksite_ID"],
                "status": ustatus,
                "green": u["green"],
                "yellow": u["yellow"],
                "red": u["red"],
                "total": u["total"],
            })

        # Per-employee levers for borderline (yellow) employees.
        floor_hours = pack.min_weekly_hours
        floor_wages = pack.min_weekly_wages
        for e in perf["employees"]:
            if e["status"] != "yellow":
                continue
            parts = []
            if e["hours_gap_per_week"] > 0:
                parts.append(
                    f"add {e['hours_gap_per_week']:.1f} hrs/wk to clear the {st} {floor_hours:.0f}-hr threshold"
                )
            if floor_wages > 0 and e["wages_gap_per_week"] > 0:
                parts.append(
                    f"raise weekly wages by ${e['wages_gap_per_week']:,.0f} to clear the {st} ${floor_wages:,.0f}/wk floor"
                )
            if not parts:
                continue
            lever = (
                f"{e['Employee_ID']} ({e['Worksite_ID']}) is at {e['avg_weekly_hours']:.1f} hrs/wk "
                f"and ${e['avg_weekly_wages']:,.0f}/wk avg — " + "; ".join(parts) + "."
            )
            employee_levers.append({
                "state": st,
                "Employee_ID": e["Employee_ID"],
                "Worksite_ID": e["Worksite_ID"],
                "avg_weekly_hours": e["avg_weekly_hours"],
                "avg_weekly_wages": e["avg_weekly_wages"],
                "hours_gap_per_week": e["hours_gap_per_week"],
                "wages_gap_per_week": e["wages_gap_per_week"],
                "annual_hours_to_qualify": e["annual_hours_to_qualify"],
                "lever": lever,
            })

    employee_levers.sort(key=lambda x: x["hours_gap_per_week"])  # smallest gap = easiest win first
    return {
        "as_of": date.today().isoformat(),
        "tax_year": tax_year,
        "cadence": "monthly",
        "anchored_on": "state measuring date (one_zero.measuring_date; default last day of month)",
        "unit_status_counts": status_counts,
        "unit_alerts": unit_alerts,
        "at_risk_employee_count": len(employee_levers),
        "employee_levers": employee_levers[:50],
        "_roadmap_tag": "J3",
        "source": (
            "UX-03: monthly cadence on the magical pay date; alerts distinguish "
            "on-track / at-risk / exceeding and name the specific lever to clear "
            "the threshold (e.g. 'add overtime to clear SC 32-hr threshold')."
        ),
    }


@router.get("/triggers")
def triggers(account_id: int | None = None) -> dict[str, Any]:
    """Trigger detection: diff prior vs current pay-period snapshots and surface
    the opportunity flags (headcount spike, wage increase, new FEIN, new
    jurisdiction)."""
    from tools.triggers import detect_triggers

    rows = require_pay_periods(account_id=account_id)
    prior_rows = [r for r in rows if r["Tax_Year"] == 2024]
    current_rows = [r for r in rows if r["Tax_Year"] == 2025]
    detected = detect_triggers(prior_rows, current_rows)

    by_type: dict[str, int] = {}
    for t in detected:
        by_type[t["type"]] = by_type.get(t["type"], 0) + 1

    return {
        "as_of": date.today().isoformat(),
        "prior_snapshot": "Tax year 2024 (Q4 only)",
        "current_snapshot": "Tax year 2025 (full)",
        "trigger_count": len(detected),
        "by_type": by_type,
        "triggers": detected,
        "source": (
            "Per the stakeholder meeting (5/29): triggers replace static alerts "
            "with a real differ over consecutive payroll snapshots. Production "
            "runs nightly via Azure Function."
        ),
    }


@router.get("/performance/{tax_year}")
def performance_dashboard(
    tax_year: int,
    state: str | None = None,
    worksite: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """Performance Dashboard data: per-employee green /
    yellow / red classification + per-unit color split + hours-to-qualify.

    [O1] UX-05 — `worksite` scopes the rows server-side to a single site, so a
    field/operational persona scoped to one location sees ONLY that location's
    employees (store A can't see store B). [O3] adds the dollarized yellow lever.
    """
    from domain.calculation.onezero import run_performance_dashboard
    from tools.credit_math import state_per_job_usd

    rows = require_pay_periods(drop_qc=True, account_id=account_id)
    rows = [r for r in rows if r["Tax_Year"] == tax_year]
    if worksite:
        rows = [r for r in rows if r.get("Worksite_ID") == worksite]  # [O1] row scope

    by_state: list[dict[str, Any]] = []
    for st, pack, state_rows in iter_state_packs(rows, tax_year=tax_year, state=state):
        result = run_performance_dashboard(
            state_rows, tax_year=tax_year, pack=pack, per_job_usd=state_per_job_usd(st),
        )
        result["state"] = st
        result["yellow_credit_at_stake_usd"] = sum(  # [O3]
            e["credit_at_stake_usd"] for e in result["employees"] if e["status"] == "yellow"
        )
        by_state.append(result)

    totals = {"green": 0, "yellow": 0, "red": 0, "total": 0}
    yellow_at_stake_total = 0
    for s in by_state:
        for k in ("green", "yellow", "red"):
            totals[k] += s["summary"][k]
        totals["total"] += s["employee_count"]
        yellow_at_stake_total += s.get("yellow_credit_at_stake_usd", 0)

    return {
        "as_of": date.today().isoformat(),
        "tax_year": tax_year,
        "scoped_worksite": worksite,        # [O1] echoes the row scope (None = all)
        "totals": totals,
        "yellow_credit_at_stake_usd": yellow_at_stake_total,  # [O3]
        "states": by_state,
        "anonymization_note": (
            "Employee_ID values shown are synthetic prototype tokens (E00001 ...). "
            "The pay-period CSV omits SSN, names, and hire/term dates by design "
            "(see the BCS business-framing overview, 'Anonymity of PII'). Production "
            "tokenizes Employee_ID at the ingestion boundary; per-employee detail "
            "is releasable only under audit to authorized personnel."
        ),
    }
