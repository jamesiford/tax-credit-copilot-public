"""The retroactive scan - what was left on the table in prior years.

Split out of `api/onezero.py`. Each year is priced under the statute in force
THAT year, never today's [ADR-005]. A year with no authored rule pack is
declined by name and reported, so a partial sweep is never presented as a
complete one.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter

from api._payperiods import (
    iter_state_packs,
    require_pay_periods,
    unauthored_state_years,
)
from data.claims import get_all_claims

router = APIRouter(prefix="/api", tags=["retroactive"])


@router.get("/onezero/retroactive/scan")
def one_zero_retroactive_scan(account_id: int | None = None) -> dict[str, Any]:
    """Retroactive multi-tax-year scan: replay the One/Zero across every prior
    year in the dataset and surface unclaimed-but-triggered credits — the
    stakeholders' #1 quick win.
    """
    from domain.calculation.onezero import run_pay_period_method, fiscal_window_start, fiscal_year_of
    from tools.credit_math import load_pack_one_zero, apply_one_zero_state_credit
    from config import get_fiscal_year_end_month

    fy_end_month = get_fiscal_year_end_month()
    all_rows = require_pay_periods(drop_qc=True, account_id=account_id)

    # Bucket every row into its fiscal year by PAY DATE (same rule as the main
    # /api/onezero endpoint and CALC-05), so the retroactive scan and the live
    # Headcount panel agree on each state-year's Average Headcount.
    def _fy(row: dict[str, Any]) -> int:
        return fiscal_year_of(date.fromisoformat(str(row["Pay_Date"])[:10]), fy_end_month)

    rows_by_fy: dict[int, list[dict[str, Any]]] = {}
    for r in all_rows:
        rows_by_fy.setdefault(_fy(r), []).append(r)
    # Only scan years with material data (drops the tiny Dec→Jan spillover sliver).
    tax_years = sorted(fy for fy, rs in rows_by_fy.items() if len(rs) >= 200)
    existing = {(c["jurisdiction"], c.get("tax_year")) for c in get_all_claims()}

    # [ADR-005] The years above come from the payroll, and payroll routinely runs
    # past the last year a legislature has published a wage table for. Those years
    # are DECLINED, not skipped: they are named in the response so the report does
    # not merely look complete. One uncovered year must not take down the rest.
    declined = unauthored_state_years(tax_years)

    # First pass: per-(state, fiscal-year) Average Headcount, so each year's
    # credit can net against the PRIOR year's headcount (net-new) rather than
    # treating the whole workforce as new. A year with no prior-year entry (the
    # earliest year in the dataset, or a brand-new state) nets against 0 — the
    # establishment-year case, where the full headcount legitimately counts.
    avg_by_state_year: dict[tuple[str, int], float] = {}
    for ty in tax_years:
        ty_rows = rows_by_fy.get(ty, [])
        for st, pack, state_rows in iter_state_packs(ty_rows, tax_year=ty, on_unauthored="skip"):
            if len(state_rows) < 50:  # ignore tiny windows
                continue
            pp = run_pay_period_method(
                state_rows, tax_year=ty,
                analysis_start_month=fiscal_window_start(ty, fy_end_month), pack=pack,
                fiscal_year_end_month=fy_end_month,
            )
            avg_by_state_year[(st, ty)] = pp.annual_average

    opportunities: list[dict[str, Any]] = []
    for ty in tax_years:
        ty_rows = rows_by_fy.get(ty, [])
        for st, pack, state_rows in iter_state_packs(ty_rows, tax_year=ty, on_unauthored="skip"):
            if len(state_rows) < 50:  # ignore tiny windows (Q4-only retros)
                continue
            avg = avg_by_state_year.get((st, ty), 0.0)
            prior_avg = avg_by_state_year.get((st, ty - 1), 0.0)
            credit = apply_one_zero_state_credit(st, avg, prior_period_average_headcount=prior_avg)
            if credit.get("annual_credit_usd", 0) <= 0:
                continue
            already_filed = (st, ty) in existing
            opportunities.append({
                "tax_year": ty,
                "state": st,
                "credit_code": credit["credit_code"],
                "credit_name": credit["credit_name"],
                "citation": credit["citation"],
                "average_headcount": avg,
                "prior_year_average_headcount": prior_avg,
                "qualifying_jobs": credit["qualifying_jobs"],
                "annual_credit_usd": credit["annual_credit_usd"],
                "lifetime_credit_usd": credit["lifetime_credit_usd"],
                "already_filed": already_filed,
                "status": "filed" if already_filed else "unclaimed_retroactive",
            })

    unclaimed = [o for o in opportunities if not o["already_filed"]]
    total_unclaimed_lifetime = sum(o["lifetime_credit_usd"] for o in unclaimed)

    # [N1] RETRO-01 / DISC-15 — frozen-base-year tranche reconstruction. Run the
    # base-year engine across the available years per state so a job created in
    # an early year still surfaces its current/out-year claimable installments
    # (GA: refund 1 year back, but a 5-year-old creation still throws an
    # installment within its tranche window — the reason to scan years back).
    from tools.baseyear import compute_base_year_tranches
    tranche_analysis: list[dict[str, Any]] = []
    states_seen = sorted({st for (st, _ty) in avg_by_state_year})
    for st in states_seen:
        yearly_avg = {ty: avg_by_state_year[(s, ty)] for (s, ty) in avg_by_state_year if s == st}
        if len(yearly_avg) < 2:
            continue
        base_year = min(yearly_avg)
        sample = apply_one_zero_state_credit(st, yearly_avg[max(yearly_avg)])
        per_job = float(sample.get("amount_per_job_usd") or 0.0)
        threshold = float(sample.get("threshold") or 0.0)
        if per_job <= 0:
            continue
        result = compute_base_year_tranches(
            st, yearly_avg, base_year=base_year, threshold=threshold, per_job_usd=per_job,
        )
        tranche_analysis.append(result.to_dict())

    return {
        "as_of": date.today().isoformat(),
        "tax_years_scanned": [ty for ty in tax_years if ty not in declined],
        "declined_years": [
            {
                "tax_year": ty,
                "states": sorted(states),
                "reason": "no_authored_statute",
                "detail": next(iter(states.values())),
            }
            for ty, states in sorted(declined.items())
        ],
        "opportunities": sorted(opportunities, key=lambda o: o["lifetime_credit_usd"], reverse=True),
        "summary": {
            "total_opportunities": len(opportunities),
            "unclaimed_count": len(unclaimed),
            "total_unclaimed_lifetime_usd": total_unclaimed_lifetime,
            "declined_year_count": len(declined),
        },
        "tranche_analysis": tranche_analysis,  # [N1] RETRO-01 frozen-base reconstruction
    }
