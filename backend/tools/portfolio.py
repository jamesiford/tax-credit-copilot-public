"""Statutory portfolio builder — the single source of truth for the
multi-state credit picture shown on Discovery, Credit Portfolio, the Overview
KPI strip, and billing.

This replaces the retired FTE-proxy (`tools/headcount.py:compute_avg_monthly_fte`
+ `tools/credit_math.py:apply_state_credit`). Every tile here is produced by the
statutory **One/Zero Base Calculation** engine over the BCS-shaped pay-period
feed, with credit computed on the **net-new** year-over-year change in Average
Monthly Headcount — the method states actually accept. No invented metric.

Tile shape is kept compatible with what the frontend consumed from the old
`/api/eligibility` jurisdictions[] tiles (code, name, jurisdiction, citation,
basis, metric_label/value/sublabel, qualifying_jobs, threshold, per_job_label,
annual_credit_usd, lifetime_credit_usd, benefit_period_years, trend,
calculation_trail, filing, why_surfaced) so the UI needs no contract change.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from infrastructure.payroll.pay_period_source import load_pay_periods
from domain.calculation.onezero import (
    run_pay_period_method,
    fiscal_year_of,
    fiscal_window_start,
)
from tools.credit_math import STATE_TO_PACK, load_pack_one_zero, apply_one_zero_state_credit

_RULES = Path(__file__).resolve().parent.parent / "rules"
_PAYROLL_CSV = Path(__file__).resolve().parent.parent / "data" / "payroll.csv"
_FEDERAL_PACK_FILE = "federal_wotc_lite.json"


def _load_pack_json(filename: str) -> dict[str, Any]:
    path = _RULES / filename
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _federal_new_hires(tax_year: int) -> int:
    """Count genuine new hires in the tax year from payroll.csv hire_date.

    WOTC (IRC §51) is a per-qualifying-hire credit keyed on the hire date, which
    lives in payroll.csv (the BCS pay-period feed omits hire_date by design).
    This is the honest new-hire count, not a pay-period first-appearance proxy.
    """
    if not _PAYROLL_CSV.exists():
        return 0
    count = 0
    with _PAYROLL_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hd = (r.get("hire_date") or "").strip()
            if hd[:4] == str(tax_year):
                count += 1
    return count


def _state_avg_headcount(rows: list[dict], *, tax_year: int, state: str, pack, fy_end_month: int):
    """Run the One/Zero pay-period method for one state-year and return the
    OneZeroResult (or None if no rows)."""
    state_rows = [r for r in rows if r["Worksite_ID"].startswith(f"{state}_")]
    if not state_rows:
        return None
    return run_pay_period_method(
        state_rows,
        tax_year=tax_year,
        analysis_start_month=fiscal_window_start(tax_year, fy_end_month),
        pack=pack,
        fiscal_year_end_month=fy_end_month,
    )


def _monthly_trend(result) -> list[float]:
    """12-month Average Headcount trend (sum of unit month-totals) for a sparkline."""
    if result is None or not result.summary:
        return [0.0] * 12
    trend = [0.0] * 12
    for unit_row in result.summary:
        for m, v in enumerate(unit_row["month_totals"][:12]):
            trend[m] += v
    return [round(v, 2) for v in trend]


def _state_tile(
    rows_cur: list[dict],
    rows_prior: list[dict],
    *,
    state: str,
    tax_year: int,
    fy_end_month: int,
) -> dict[str, Any] | None:
    """Build a statutory tile for one state pack via the One/Zero engine."""
    pack = load_pack_one_zero(state, tax_year=tax_year)
    if pack is None:
        return None
    cur = _state_avg_headcount(rows_cur, tax_year=tax_year, state=state, pack=pack, fy_end_month=fy_end_month)
    if cur is None:
        return None

    prior_pack = load_pack_one_zero(state, tax_year=tax_year - 1)
    prior = _state_avg_headcount(rows_prior, tax_year=tax_year - 1, state=state, pack=prior_pack, fy_end_month=fy_end_month) if prior_pack else None
    prior_avg = prior.annual_average if prior is not None else 0.0

    credit = apply_one_zero_state_credit(state, cur.annual_average, prior_period_average_headcount=prior_avg)

    pack_json = _load_pack_json(STATE_TO_PACK[state])
    threshold = float(pack_json["thresholds"]["minimum_new_jobs"])
    net_new = round(max(0.0, cur.annual_average - prior_avg), 2)
    trend = _monthly_trend(cur)
    part_time = sum(1 for e in cur.eligible_employees if e.get("weight", 1.0) < 1.0)

    # Audit trail: the statutory steps the engine just recorded would be ideal,
    # but we assemble a compact, citation-bearing walk here so the tile is
    # self-contained for the Audit/Evidence views.
    trail = [
        {
            "step": f"Run statutory One/Zero Base Calculation ({state} {tax_year})",
            "inputs": {"eligible_employees": len(cur.eligible_employees), "part_time_half_weight": part_time},
            "formula": "per-employee 1/0.5/0 by unit per month → Average Monthly Headcount = mean of 12 monthly unit counts",
            "output": {"average_headcount": cur.annual_average},
            "citation": pack.citation,
        },
        {
            "step": f"Net-new vs prior year ({tax_year - 1})",
            "inputs": {"current_avg_headcount": cur.annual_average, "prior_avg_headcount": prior_avg},
            "formula": "net_new = max(0, current_avg_headcount - prior_avg_headcount)",
            "output": {"net_new": net_new},
            "citation": pack.citation,
        },
        {
            "step": f"Apply {int(threshold)}-job statutory threshold",
            "inputs": {"net_new": net_new, "threshold": threshold},
            "formula": "qualifying_jobs = max(0, net_new - threshold)",
            "output": {"qualifying_jobs": credit["qualifying_jobs"]},
            "citation": pack.citation,
        },
        {
            "step": f"Apply benefit math ({pack_json['credit']['name']})",
            "inputs": {"qualifying_jobs": credit["qualifying_jobs"], "amount_per_job_usd": credit.get("amount_per_job_usd")},
            "formula": "annual = qualifying_jobs * amount_per_job; lifetime = annual * benefit_years",
            "output": {"annual_credit_usd": credit["annual_credit_usd"], "lifetime_credit_usd": credit["lifetime_credit_usd"]},
            "citation": pack.citation,
        },
    ]

    return {
        "code": credit["credit_code"],
        "name": credit["credit_name"],
        "jurisdiction": state,
        "citation": credit["citation"],
        "basis": "net_new_headcount",
        "metric_label": "Avg monthly headcount",
        "metric_value": cur.annual_average,
        "metric_sublabel": f"Prior year {prior_avg} · {len(cur.eligible_employees)} eligible employees",
        "qualifying_jobs": credit["qualifying_jobs"],
        "threshold": threshold,
        "per_job_label": f"${credit.get('amount_per_job_usd', 0):,.0f} per qualifying job",
        "annual_credit_usd": credit["annual_credit_usd"],
        "lifetime_credit_usd": credit["lifetime_credit_usd"],
        "benefit_period_years": credit["benefit_period_years"],
        "average_headcount": cur.annual_average,
        "prior_year_average_headcount": prior_avg,
        "net_new_headcount": net_new,
        "part_time_eligible_count": part_time,
        "trend": trend,
        "calculation_trail": trail,
        "filing": pack_json.get("filing") or {"window": "See rule pack", "cycle": "unspecified"},
        "why_surfaced": (
            f"{net_new} net-new average headcount (current {cur.annual_average} vs prior {prior_avg}) "
            f"vs {int(threshold)}-job threshold → {credit['qualifying_jobs']} qualifying"
        ),
    }


def _federal_tile(rows_cur: list[dict], rows_prior: list[dict], *, tax_year: int) -> dict[str, Any] | None:
    """Federal WOTC tile. WOTC (IRC §51) is a per-qualifying-hire credit keyed on
    the hire date, counted from payroll.csv hire_date within the tax year."""
    pack = _load_pack_json(_FEDERAL_PACK_FILE)
    if not pack:
        return None
    gross_hires = _federal_new_hires(tax_year)

    threshold = float(pack["thresholds"]["minimum_new_jobs"])
    # WOTC applies only to hires certified in a target group — apply the
    # documented illustrative certification rate from the pack (not 100%).
    rate = float(pack["benefit"].get("wotc_target_group_qualification_rate", 1.0))
    new_hires = round(gross_hires * rate)
    if new_hires < threshold:
        return None
    per_job = float(pack["benefit"]["amount_per_qualifying_job_usd"])
    years = int(pack["benefit"]["benefit_period_years"])
    citation = pack["credit"]["statutory_citation"]
    annual = round(new_hires * per_job)
    lifetime = annual * years

    trail = [
        {
            "step": "Identify new hires in the federal window",
            "inputs": {"tax_year": tax_year},
            "formula": "count employees with hire_date in tax_year (payroll.csv)",
            "output": {"gross_new_hires": gross_hires},
            "citation": "synthetic payroll.csv hire_date; per-hire WOTC basis",
        },
        {
            "step": "Apply illustrative WOTC target-group certification rate",
            "inputs": {"gross_new_hires": gross_hires, "target_group_rate": rate},
            "formula": "qualifying_hires = round(gross_new_hires * target_group_rate)",
            "output": {"qualifying_hires": new_hires},
            "citation": "DOL ETA 9061/9062 target-group screening (illustrative rate; see pack)",
        },
        {
            "step": "Apply per-hire federal credit amount",
            "inputs": {"new_hires": new_hires, "amount_per_hire_usd": per_job},
            "formula": "new_hires * amount_per_hire_usd",
            "output": {"annual_credit_usd": annual},
            "citation": citation,
        },
        {
            "step": f"Project over {years}-year benefit period",
            "inputs": {"annual_credit_usd": annual, "benefit_period_years": years},
            "formula": "annual_credit_usd * benefit_period_years",
            "output": {"lifetime_credit_usd": lifetime},
            "citation": citation,
        },
    ]
    return {
        "code": pack["credit"]["code"],
        "name": pack["credit"]["name"],
        "jurisdiction": pack["jurisdiction"]["code"],
        "citation": citation,
        "basis": "new_hires_in_window",
        "metric_label": f"WOTC-eligible hires ({tax_year})",
        "metric_value": new_hires,
        "metric_sublabel": f"~{rate:.0%} of {gross_hires} gross new hires (target-group certified)",
        "qualifying_jobs": new_hires,
        "threshold": threshold,
        "per_job_label": f"${per_job:,.0f} per hire",
        "annual_credit_usd": annual,
        "lifetime_credit_usd": lifetime,
        "benefit_period_years": years,
        "trend": [0.0] * 12,
        "calculation_trail": trail,
        "filing": pack.get("filing") or {"window": "See rule pack", "cycle": "unspecified"},
        "why_surfaced": (
            f"{gross_hires} new hires in {tax_year}; ~{new_hires} expected WOTC-certified "
            f"at the illustrative {rate:.0%} target-group rate"
        ),
    }


def _no_pack_tile(state: str, employee_count: int) -> dict[str, Any]:
    """Tile for a state with employees but no state-level rule pack (e.g. TX)."""
    return {
        "code": f"{state}_NO_PACK",
        "name": f"{state}: no state rule pack in library",
        "jurisdiction": state,
        "citation": "n/a — federal credits (WOTC) still apply",
        "basis": "no_pack",
        "metric_label": "Eligible employees",
        "metric_value": employee_count,
        "metric_sublabel": f"{employee_count} {state} employees · no state JTC equivalent in library",
        "qualifying_jobs": 0,
        "threshold": 0,
        "per_job_label": "—",
        "annual_credit_usd": 0,
        "lifetime_credit_usd": 0,
        "benefit_period_years": 0,
        "trend": [0.0] * 12,
        "calculation_trail": [
            {
                "step": f"Look up state rule pack for {state}",
                "inputs": {"state": state, "library": sorted(STATE_TO_PACK.keys())},
                "formula": "STATE_TO_PACK[state]",
                "output": {"pack": None, "fallback": "federal-only"},
                "citation": "backend/rules/",
            },
        ],
        "filing": {"window": "n/a — no state rule pack", "cycle": "federal-only"},
        "why_surfaced": f"No state rule pack for {state}; federal WOTC still applies",
    }


def latest_tax_year(fy_end_month: int = 12, *, account_id: int | None = None) -> int:
    """Most recent fiscal year with a *substantial* slice of the pay-period feed
    (the year the portfolio defaults to). Thin tails — pay periods that spill
    into the following January — are ignored so we don't default to a near-empty
    fiscal year. Falls back to the prior calendar year if no data."""
    all_rows = load_pay_periods(account_id)
    counts: dict[int, int] = {}
    for r in all_rows:
        fy = fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month)
        counts[fy] = counts.get(fy, 0) + 1
    if not counts:
        return date.today().year - 1
    busiest = max(counts.values())
    substantial = [fy for fy, n in counts.items() if n >= busiest * 0.5]
    return max(substantial)


def build_portfolio(
    tax_year: int,
    *,
    fy_end_month: int = 12,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    """Build the full multi-jurisdiction portfolio for a tax year, statutory engine.

    Returns the list of jurisdiction tiles (state packs that have data, the
    federal WOTC tile, and a no-pack tile per state-with-employees that has no
    rule pack), matching the legacy `/api/eligibility` jurisdictions[] shape.
    """
    all_rows = load_pay_periods(account_id)
    rows_cur = [r for r in all_rows if fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month) == tax_year]
    rows_prior = [r for r in all_rows if fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month) == tax_year - 1]

    tiles: list[dict[str, Any]] = []
    state_packs_seen: set[str] = set()

    for state in sorted(STATE_TO_PACK.keys()):
        tile = _state_tile(rows_cur, rows_prior, state=state, tax_year=tax_year, fy_end_month=fy_end_month)
        if tile:
            tiles.append(tile)
            state_packs_seen.add(state)

    fed = _federal_tile(rows_cur, rows_prior, tax_year=tax_year)
    if fed:
        tiles.append(fed)

    # No-pack states (employees present, no rule pack — e.g. TX).
    states_with_rows: dict[str, int] = {}
    for r in rows_cur:
        st = r["Worksite_ID"].split("_", 1)[0]
        states_with_rows[st] = states_with_rows.get(st, 0) + 1
    for st in sorted(states_with_rows):
        if st not in state_packs_seen and st not in ("US",):
            # count distinct employees, not rows
            ee = len({r["Employee_ID"] for r in rows_cur if r["Worksite_ID"].startswith(f"{st}_")})
            tiles.append(_no_pack_tile(st, ee))

    return tiles


def chat_jobs_at_risk(
    *,
    account_id: int,
    state: str,
    tax_year: int,
    method: str = "min_max",
    within_weekly_hours: float = 5.0,
    limit: int = 10,
) -> dict[str, Any]:
    """Which counted jobs sit close enough to a floor to fall out, READ.

    "Are any of the net-new jobs close to the threshold and therefore may fall
    off" is a question about the people already INSIDE the credit. The
    near-miss cohort cannot answer it — that is everybody outside.
    """
    from application.queries._client_run import ClientRunNotAvailable, resolve_statute
    from application.wiring import get_gold_reader
    from domain.calculation.proximity import fragile_cohort

    try:
        resolved = resolve_statute(
            account_id=account_id, state=state.upper(), tax_year=tax_year
        )
    except ClientRunNotAvailable as exc:
        return {"calculated": False, "declined": str(exc)}

    floors = resolved.floors
    read = get_gold_reader().at_risk(
        account_id,
        tax_year=tax_year,
        method=method,
        min_weekly_hours=float(floors.min_weekly_hours),
        min_weekly_wages=float(floors.min_weekly_wages),
    )
    counts = read["counts"]
    if read["run"] is None or counts is None or not int(counts.get("eligible_count") or 0):
        return {"calculated": False, "client_id": account_id, "tax_year": tax_year}

    averages = [
        {
            "Employee_ID": row["employee_id"],
            "record_token": row["record_token"],
            "weeks_worked": float(row["weeks_worked"] or 0),
            "total_hours": float(row["total_hours"] or 0),
            "total_wages": float(row["total_wages"] or 0),
            "avg_weekly_hours": float(row["avg_weekly_hours"] or 0),
            "avg_weekly_wages": float(row["avg_weekly_wages"] or 0),
            "weight": float(row["weight"] or 1),
        }
        for row in read["rows"]
    ]

    cohort = fragile_cohort(
        averages,
        floors=floors,
        within_weekly_hours=within_weekly_hours,
        limit=limit,
        population={
            "evaluated": int(counts["evaluated"] or 0),
            "eligible": int(counts["eligible_count"] or 0),
        },
    )
    return {
        "calculated": True,
        "client_id": account_id,
        "tax_year": tax_year,
        "state": resolved.state,
        "program_code": resolved.program_code,
        "method": method,
        **cohort,
    }


def chat_client_trend(
    *,
    account_id: int,
    method: str = "pay_period",
) -> dict[str, Any]:
    """How a client has moved across years, READ.

    "Have they been eligible since their base year" is a question about a
    SERIES. Answering it from a single-year read is how a chat ends up
    describing one year as though it were the whole history — which is exactly
    what the old single-intent router did with any follow-up question.
    """
    from application.wiring import get_gold_reader

    series = get_gold_reader().client_year_series(account_id, method=method)
    years = series["years"]
    if not years:
        return {"calculated": False, "client_id": account_id, "method": method}

    base = next((y for y in years if y["is_base_year"]), None)
    after_base = [y for y in years if base is None or y["tax_year"] > base["tax_year"]]
    return {
        "calculated": True,
        "client_id": account_id,
        "method": method,
        "base_tax_year": base["tax_year"] if base else None,
        "years": years,
        "years_held": len(years),
        "years_after_base": len(after_base),
        # None, not False, when the run holds nothing after the base year.
        # `False` there asserts "they have not been eligible since"; the truth
        # is that there is no year to judge, and the reference client — which
        # holds TY2023 and nothing else — hits this on every read.
        "eligible_every_year_since_base": (
            all(y["eligible_employees"] > 0 for y in after_base) if after_base else None
        ),
        "years_with_no_eligible_employees": [
            y["tax_year"] for y in after_base if y["eligible_employees"] == 0
        ],
        # A year absent from the run is not a year with a zero. Stated so the
        # agent cannot narrate a gap as a decline.
        "note": (
            "Years absent from this list were not reached by the run. They "
            "carry no figure, which is not the same as a zero. Where "
            "`eligible_every_year_since_base` is null there is no year after "
            "the base year to judge — say so rather than reporting a verdict."
        ),
    }


def chat_client_context(
    *,
    account_id: int,
    tax_year: int,
    method: str = "pay_period",
) -> dict[str, Any]:
    """What the run concluded about this client-year, READ.

    The chat used to narrate `load_payroll_snapshot`, which reads a synthetic
    CSV and says so in its own citation — so the answer described 9,477
    invented employees while the question was about a client with 10,236. Same
    class of defect as the ingestion view counting Fabric rows and then running
    the next three stages over the fixture.

    Returns `calculated: False` rather than zeroes when no run has reached this
    client-year. A chat answer of "$0" and "we have not looked" are different
    statements and only one of them is safe to say to a client.
    """
    from application.wiring import get_gold_reader

    reader = get_gold_reader()
    current = reader.headcount_series(account_id, tax_year=tax_year, method=method)
    if current["run"] is None or current["annual_average"] is None:
        return {"calculated": False, "client_id": account_id, "tax_year": tax_year}

    prior = reader.headcount_series(account_id, tax_year=tax_year - 1, method=method)
    return {
        "calculated": True,
        "client_id": account_id,
        "tax_year": tax_year,
        "method": method,
        "current_average": float(current["annual_average"]),
        "prior_average": float(prior["annual_average"] or 0.0),
        "has_prior_year": prior["annual_average"] is not None,
        "month_ends": current["month_ends"],
        "run_id": (current["run"] or {}).get("run_id"),
        "produced_at": str((current["run"] or {}).get("produced_at") or ""),
    }


def chat_state_credit(
    state: str,
    *,
    tax_year: int | None = None,
    fy_end_month: int = 12,
    account_id: int | None = None,
    current_average: float | None = None,
    prior_average: float | None = None,
) -> dict[str, Any]:
    """Single-state statutory credit for the chat eligibility intent.

    Applies the rule-pack benefit math (net-new) to the year's average headcount
    and the prior year's. Returns the `apply_one_zero_state_credit` dict, or a
    `no_state_pack` dict for states with no rule pack (e.g. TX).

    Both averages may be supplied by a caller that has READ them from the run
    that computed them, in which case no payroll is replayed. Without them this
    still runs the One/Zero engine for both years, which is what every chat
    message used to cost.
    """
    state_u = state.upper()
    if tax_year is None:
        tax_year = latest_tax_year(fy_end_month, account_id=account_id)
    if state_u not in STATE_TO_PACK:
        return {
            "state": state_u,
            "no_state_pack": True,
            "credit_code": None,
            "annual_credit_usd": 0,
            "lifetime_credit_usd": 0,
            "message": (
                f"No state rule pack for {state_u}. Supported states: "
                f"{', '.join(sorted(STATE_TO_PACK.keys()))}. Federal WOTC still applies."
            ),
        }

    if current_average is not None:
        cur_avg = float(current_average)
        prior_avg = float(prior_average or 0.0)
    else:
        all_rows = load_pay_periods(account_id)
        rows_cur = [r for r in all_rows if fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month) == tax_year]
        rows_prior = [r for r in all_rows if fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month) == tax_year - 1]

        pack = load_pack_one_zero(state_u, tax_year=tax_year)
        cur = _state_avg_headcount(rows_cur, tax_year=tax_year, state=state_u, pack=pack, fy_end_month=fy_end_month)
        cur_avg = cur.annual_average if cur is not None else 0.0

        prior_pack = load_pack_one_zero(state_u, tax_year=tax_year - 1)
        prior = _state_avg_headcount(rows_prior, tax_year=tax_year - 1, state=state_u, pack=prior_pack, fy_end_month=fy_end_month) if prior_pack else None
        prior_avg = prior.annual_average if prior is not None else 0.0

    return apply_one_zero_state_credit(state_u, cur_avg, prior_period_average_headcount=prior_avg)
