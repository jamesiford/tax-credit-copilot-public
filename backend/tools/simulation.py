"""Hypothetical-hire simulation: 'what if we hired N more people in <city>?'

Projects how a net change in headcount at a location would change the statutory
credit, using the One/Zero Base Calculation engine (net-new Average Monthly
Headcount above the rule-pack threshold) — the same auditable engine that drives
the rest of the portfolio. Pure Python; no LLM involvement.
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .credit_math import apply_one_zero_state_credit
from .portfolio import chat_state_credit
from domain.calculation.trail import current_recorder

# Coarse city -> (state, county) mapping for the demo.
_CITY_MAP = {
    # GA
    "atlanta": ("GA", "Fulton"),
    "savannah": ("GA", "Chatham"),
    "macon": ("GA", "Bibb"),
    # NY
    "new york": ("NY", "New York"),
    "brooklyn": ("NY", "Kings"),
    # SC
    "charleston": ("SC", "Charleston"),
    "greenville": ("SC", "Greenville"),
    # TX
    "austin": ("TX", "Travis"),
    "houston": ("TX", "Harris"),
    "dallas": ("TX", "Dallas"),
    # NC (Phase A expansion)
    "charlotte": ("NC", "Mecklenburg"),
    "raleigh": ("NC", "Wake"),
    # TN
    "nashville": ("TN", "Davidson"),
    "memphis": ("TN", "Shelby"),
    # FL
    "jacksonville": ("FL", "Duval"),
    "miami": ("FL", "Miami-Dade"),
    "orlando": ("FL", "Orange"),
    # OH
    "columbus": ("OH", "Franklin"),
    "cincinnati": ("OH", "Hamilton"),
    "cleveland": ("OH", "Cuyahoga"),
    # CO
    "denver": ("CO", "Denver"),
    "boulder": ("CO", "Boulder"),
    # VA
    "tysons": ("VA", "Fairfax"),
    "tysons corner": ("VA", "Fairfax"),
    "richmond": ("VA", "Richmond"),
    "arlington": ("VA", "Arlington"),
}


def _resolve_location(city_or_state: str) -> tuple[str, str | None]:
    key = (city_or_state or "").strip().lower()
    if key in _CITY_MAP:
        return _CITY_MAP[key]
    if len(key) == 2:
        return (key.upper(), None)
    return ("GA", "Fulton")  # demo default


def simulate_hiring(
    location: Annotated[str, Field(description="City name (e.g. 'Atlanta') or two-letter state code.")],
    new_hires: Annotated[int, Field(description="Net change in headcount (negative = layoff/close).", ge=-500, le=500)],
) -> dict[str, Any]:
    """Project how a net change in headcount at `location` would change the
    statutory credit.

    Positive `new_hires` adds to the state's current-year Average Monthly
    Headcount; negative simulates layoffs / a site closure. Baseline and
    projected credits both run through the One/Zero net-new engine. Returns
    baseline credit, projected credit, and the USD delta.
    """
    if new_hires == 0:
        raise ValueError("new_hires must be non-zero")
    state, county = _resolve_location(location)

    baseline = chat_state_credit(state)
    no_pack = bool(baseline.get("no_state_pack"))

    if no_pack:
        baseline_avg = 0.0
        prior_avg = 0.0
        baseline_credit = {"annual_credit_usd": 0, "lifetime_credit_usd": 0,
                           "citation": "n/a — no state rule pack (federal WOTC still applies)"}
        projected_credit = dict(baseline_credit)
        projected_net_new = 0.0
    else:
        baseline_avg = float(baseline.get("average_headcount", 0.0))
        prior_avg = float(baseline.get("prior_period_average_headcount", 0.0))
        baseline_credit = baseline
        projected_avg = round(max(0.0, baseline_avg + new_hires), 2)
        projected_credit = apply_one_zero_state_credit(state, projected_avg, prior_period_average_headcount=prior_avg)
        projected_net_new = round(max(0.0, projected_avg - prior_avg), 2)

    baseline_net_new = round(max(0.0, baseline_avg - prior_avg), 2)
    delta_annual = projected_credit["annual_credit_usd"] - baseline_credit["annual_credit_usd"]
    delta_lifetime = projected_credit["lifetime_credit_usd"] - baseline_credit["lifetime_credit_usd"]

    result = {
        "location_city_or_state": location,
        "resolved_state": state,
        "resolved_county": county,
        "new_hires": new_hires,
        "baseline": {
            "net_new_headcount": baseline_net_new,
            "average_headcount": round(baseline_avg, 2),
            "annual_credit_usd": baseline_credit["annual_credit_usd"],
            "lifetime_credit_usd": baseline_credit["lifetime_credit_usd"],
        },
        "projected": {
            "net_new_headcount": projected_net_new,
            "average_headcount": round(max(0.0, baseline_avg + new_hires), 2),
            "annual_credit_usd": projected_credit["annual_credit_usd"],
            "lifetime_credit_usd": projected_credit["lifetime_credit_usd"],
        },
        "delta": {
            "annual_credit_usd": delta_annual,
            "lifetime_credit_usd": delta_lifetime,
        },
        "citation": baseline_credit["citation"],
    }

    recorder = current_recorder()
    if recorder is not None:
        verb = "Add" if new_hires > 0 else "Remove"
        magnitude = abs(new_hires)
        recorder.title = f"What-if: {'+' if new_hires > 0 else '-'}{magnitude} headcount in {location}"
        recorder.citation = baseline_credit["citation"]
        recorder.record(
            step="Resolve location",
            inputs={"input": location},
            formula="city -> (state, county) lookup",
            output={"state": state, "county": county},
            citation="prototype city map",
        )
        recorder.record(
            step="Baseline statutory credit (as-is)",
            inputs={"average_headcount": round(baseline_avg, 2), "prior_period_average_headcount": round(prior_avg, 2)},
            formula="apply_one_zero_state_credit(baseline avg headcount, prior avg)",
            output={"lifetime_credit_usd": baseline_credit["lifetime_credit_usd"]},
            citation=baseline_credit["citation"],
        )
        recorder.record(
            step=f"{verb} {magnitude} to current-year Average Monthly Headcount",
            inputs={"baseline_average_headcount": round(baseline_avg, 2), "delta": new_hires},
            formula="projected_avg = max(0, baseline_avg + delta)",
            output={"projected_average_headcount": round(max(0.0, baseline_avg + new_hires), 2),
                    "projected_net_new_headcount": projected_net_new},
            citation="straight-line model; assumes the change persists across the year",
        )
        recorder.record(
            step="Projected statutory credit",
            inputs={"projected_net_new_headcount": projected_net_new},
            formula="apply_one_zero_state_credit(projected avg headcount, prior avg)",
            output={"lifetime_credit_usd": projected_credit["lifetime_credit_usd"]},
            citation=baseline_credit["citation"],
        )
        recorder.record(
            step="Delta",
            inputs={"baseline_lifetime": baseline_credit["lifetime_credit_usd"], "projected_lifetime": projected_credit["lifetime_credit_usd"]},
            formula="projected_lifetime - baseline_lifetime",
            output={"delta_annual_usd": delta_annual, "delta_lifetime_usd": delta_lifetime},
            citation=baseline_credit["citation"],
        )

    return result



# ---------------------------------------------------------------------------
# [J2] UX-02 — statutory One/Zero entity-level simulator helpers.
# Extracted from api/eligibility.py so the row-mutation + snapshot logic lives
# in the tool layer (the route just orchestrates). Imports are local to avoid
# a load-time cycle with tools.onezero / tools.credit_math.
# ---------------------------------------------------------------------------


def onezero_snapshot(
    rows: list[dict[str, Any]],
    *,
    tax_year: int,
    state: str,
    pack: Any,
    prior_average_headcount: float = 0.0,
) -> dict[str, Any]:
    """Run the One/Zero pay-period method + benefit math for a row set and return
    the headline figures the J2 simulator compares (baseline vs projected).

    `prior_average_headcount` is the frozen base the credit is measured against.
    **Omitting it treats the entire workforce as net-new**, which for an
    established employer overstates the credit enormously — and, worse, produces
    a different figure from the one the coverage matrix shows for the same
    client and year. Two screens disagreeing about a client's position is
    indefensible regardless of which one is right.
    """
    from datetime import date as _date

    from domain.calculation.onezero import run_pay_period_method
    from .credit_math import apply_one_zero_state_credit

    res = run_pay_period_method(
        rows, tax_year=tax_year, analysis_start_month=_date(tax_year, 1, 1), pack=pack
    )
    credit = apply_one_zero_state_credit(
        state, res.annual_average, prior_period_average_headcount=prior_average_headcount,
    )
    return {
        "average_headcount": res.annual_average,
        "eligible_employee_count": len(res.eligible_employees),
        "part_time_eligible_count": sum(1 for e in res.eligible_employees if e.get("weight", 1.0) < 1.0),
        "qualifying_jobs": credit.get("qualifying_jobs", 0),
        "annual_credit_usd": credit.get("annual_credit_usd", 0),
        "lifetime_credit_usd": credit.get("lifetime_credit_usd", 0),
        "base_average_headcount": round(prior_average_headcount, 2),
    }


def describe_role(weekly_hours: float | None, hourly_rate: float | None, pack: Any) -> str:
    """Whether a role of these hours and pay clears the two floors, in words.

    Reported, not enforced: the engine decides who counts. This only says in
    advance why a hire might move nothing.
    """
    min_hours = float(pack.min_weekly_hours)
    min_wages = float(pack.min_weekly_wages)
    if weekly_hours is not None and weekly_hours < min_hours:
        return f"below the {min_hours:g}-hour floor, so these roles will not count"
    hours = weekly_hours if weekly_hours is not None else min_hours
    if hourly_rate is not None and hours * hourly_rate < min_wages:
        return f"below the ${min_wages:,.0f}/week wage floor, so these roles will not count"
    return "clear of both floors, so each counts as a job"


def apply_onezero_lever(
    rows: list[dict[str, Any]],
    *,
    action: str,
    magnitude: float,
    pack: Any,
    state: str,
    fein: str | None = None,
    hire_weekly_hours: float | None = None,
    hire_hourly_rate: float | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return (mutated_rows, human_detail) after applying a J2 simulator lever.

    Levers: adjust_hours (hrs/wk delta), adjust_wages (percent), add_headcount
    (clone the highest-hours employee so the synthetic heads land in real major
    pay periods), remove_headcount (drop the lowest-hours employees).

    WI-22: `add_headcount` can say what the role IS — `hire_weekly_hours` and
    `hire_hourly_rate`. Each new head then works exactly those hours in every
    pay period the template held, at that rate. Absent, the old behaviour
    stands: a full-time role clear of both floors. A part-time or low-paid role
    is not refused; the engine simply does not count it, which is the answer.
    """
    import copy as _copy

    from domain.calculation.onezero import _parse_iso

    sim_rows = _copy.deepcopy(rows)
    scope_suffix = f" (FEIN {fein})" if fein else ""

    if action == "adjust_hours":
        for r in sim_rows:
            weeks = max((_parse_iso(r["Pay_Period_End"]) - _parse_iso(r["Pay_Period_Start"])).days / 7.0, 0.1)
            r["Hours_Worked"] = max(0.0, float(r["Hours_Worked"]) + magnitude * weeks)
        detail = f"Adjusted weekly hours by {magnitude:+.1f} hrs/wk across all {state} pay periods{scope_suffix}"
    elif action == "adjust_wages":
        factor = 1.0 + (magnitude / 100.0)
        for r in sim_rows:
            r["Gross_Wages"] = max(0.0, float(r["Gross_Wages"]) * factor)
        detail = f"Adjusted gross wages by {magnitude:+.1f}% across all {state} pay periods{scope_suffix}"
    elif action == "remove_headcount":
        totals: dict[str, float] = {}
        for r in sim_rows:
            totals[r["Employee_ID"]] = totals.get(r["Employee_ID"], 0.0) + float(r["Hours_Worked"])
        to_remove = {ee for ee, _ in sorted(totals.items(), key=lambda kv: kv[1])[: int(magnitude)]}
        sim_rows = [r for r in sim_rows if r["Employee_ID"] not in to_remove]
        detail = f"Removed {int(magnitude)} lowest-hours employees from {state}"
    elif action == "add_headcount":
        from collections import defaultdict as _dd

        hours_by_ee: dict[str, float] = _dd(float)
        for r in sim_rows:
            hours_by_ee[r["Employee_ID"]] += float(r["Hours_Worked"])
        if hours_by_ee:
            template_ee = max(hours_by_ee.items(), key=lambda kv: kv[1])[0]
            template_rows = [r for r in rows if r["Employee_ID"] == template_ee]
            specified = hire_weekly_hours is not None or hire_hourly_rate is not None
            template_hours = sum(float(r["Hours_Worked"]) for r in template_rows)
            template_rate = (
                sum(float(r["Gross_Wages"]) for r in template_rows) / template_hours
                if template_hours > 0 else 0.0
            )
            for n in range(int(magnitude)):
                for r in template_rows:
                    clone = dict(r)
                    clone["Employee_ID"] = f"SIM_{state}_{n:03d}"
                    if specified:
                        weeks = max(((_parse_iso(r["Pay_Period_End"]) - _parse_iso(r["Pay_Period_Start"])).days + 1) / 7.0, 1 / 7.0)
                        hours = (
                            float(hire_weekly_hours) * weeks if hire_weekly_hours is not None
                            else float(r["Hours_Worked"])
                        )
                        rate = float(hire_hourly_rate) if hire_hourly_rate is not None else template_rate
                        clone["Hours_Worked"] = max(0.0, hours)
                        clone["Gross_Wages"] = max(0.0, hours * rate)
                    else:
                        clone["Hours_Worked"] = max(float(r["Hours_Worked"]), pack.min_weekly_hours + 5.0)
                        clone["Gross_Wages"] = max(float(r["Gross_Wages"]), max(pack.min_weekly_wages, 700.0) + 50.0)
                    sim_rows.append(clone)
            if specified:
                hours_text = f"{hire_weekly_hours:g} hrs/wk" if hire_weekly_hours is not None else "the template's hours"
                rate_text = f"${hire_hourly_rate:,.2f}/hr" if hire_hourly_rate is not None else f"${template_rate:,.2f}/hr"
                role = describe_role(hire_weekly_hours, hire_hourly_rate if hire_hourly_rate is not None else template_rate, pack)
                detail = f"Added {int(magnitude)} heads at {hours_text} and {rate_text} in {state} — {role}"
            else:
                detail = f"Added {int(magnitude)} full-time heads (cloned from {template_ee}) in {state}"
        else:
            detail = "No template employee to clone; no heads added"
    else:
        detail = f"Unknown lever '{action}'; no change applied"

    return sim_rows, detail
