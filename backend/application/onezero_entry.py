"""One state's entry in the One/Zero report: the methods, the credit, the entity view.

Split out of the router that used to build all of this inline. Every function here
arranges figures the statutory engine already produced (`domain.calculation.onezero`,
`tools.credit_math`); none of them computes a new one, which is what keeps the report
agreeing with the headline number it sits beside.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from data.entities import entity_name
from domain.calculation.onezero import (
    fiscal_window_start,
    reconcile_methods,
    rollup_matrix_by_field,
    rollup_matrix_by_two_fields,
    run_min_max_method,
    run_pay_period_method,
)

ROADMAP_TAGS = ["H1", "H2", "H3", "H5", "I1", "I2", "L3", "L4"]


def apply_negotiated_override(state: str, pack: Any) -> tuple[Any, float | None, dict[str, Any] | None]:
    """[L4] CALC-10 — prefer a NEGOTIATED wage standard + minimum over the statutory pack values.

    Applied BEFORE the run so the negotiated wage floor drives eligibility.
    """
    from tools.negotiated import resolve_override

    override = resolve_override(state)
    threshold_override = None
    if override:
        if override.get("wage_standard_weekly") is not None:
            pack = dataclasses.replace(pack, min_weekly_wages=float(override["wage_standard_weekly"]))
        if override.get("min_jobs") is not None:
            threshold_override = float(override["min_jobs"])
    return pack, threshold_override, override


def run_methods(
    state_rows: list[dict[str, Any]], *, tax_year: int, pack: Any, method: str, fy_end_month: int,
) -> tuple[Any, Any]:
    """`(pay_period_result, min_max_result)`; the one not asked for is None."""
    start = fiscal_window_start(tax_year, fy_end_month)  # [H4]
    kwargs = dict(
        tax_year=tax_year, analysis_start_month=start, pack=pack, fiscal_year_end_month=fy_end_month,
    )
    pp = run_pay_period_method(state_rows, **kwargs) if method in ("pay_period", "both") else None
    mm = run_min_max_method(state_rows, **kwargs) if method in ("min_max", "both") else None
    return pp, mm


def prior_year_average(
    prior_rows: list[dict[str, Any]], state: str, *, tax_year: int, method: str, fy_end_month: int,
) -> float:
    """[H3] CALC-04 — the prior year's Average Headcount, 0.0 for an establishment year.

    Credit is computed on the YEAR-OVER-YEAR delta (the state packs are net-new-jobs
    credits). With no prior-year rows the full headcount counts, which is correct for a
    first claim.
    """
    from tools.credit_math import load_pack_one_zero

    state_rows = [r for r in prior_rows if r["Worksite_ID"].startswith(f"{state}_")]
    if not state_rows:
        return 0.0
    prior_pack = load_pack_one_zero(state, tax_year=tax_year - 1)
    if prior_pack is None:
        return 0.0
    runner = run_min_max_method if method == "min_max" else run_pay_period_method
    return runner(
        state_rows, tax_year=tax_year - 1,
        analysis_start_month=fiscal_window_start(tax_year - 1, fy_end_month),
        pack=prior_pack, fiscal_year_end_month=fy_end_month,
    ).annual_average


def headcount_figures(pp: Any, mm: Any, primary: Any, prior_avg: float) -> dict[str, Any]:
    """The method summaries, the Average Headcounts and the year-over-year delta [H1, H2, H3]."""
    return {
        "eligible_employee_count": len(primary.eligible_employees),
        "part_time_eligible_count": sum(1 for e in primary.eligible_employees if e.get("weight", 1.0) < 1.0),
        "eligibility_sample": eligibility_sample(primary),
        "pay_period_summary": pp.summary if pp else [],
        "min_max_summary": mm.summary if mm else [],
        "pay_period_average_headcount": pp.annual_average if pp else 0.0,
        "min_max_average_headcount": mm.annual_average if mm else 0.0,
        "average_headcount": primary.annual_average,
        "prior_year_average_headcount": prior_avg,
        "yoy_delta": round(primary.annual_average - prior_avg, 2),
    }


def quality_flags(pp: Any, mm: Any) -> list[Any]:
    """The data-quality flags either method raised."""
    return (pp.flags if pp else []) + (mm.flags if mm else [])


def eligibility_sample(primary: Any) -> list[dict[str, Any]]:
    """[H1] CALC-03 — per-employee eligibility test outcomes for audit."""
    return [
        {
            "Employee_ID": e["Employee_ID"],
            "avg_weekly_hours": e["avg_weekly_hours"],
            "avg_weekly_wages": e["avg_weekly_wages"],
            "passed_hours": e.get("passed_hours"),
            "passed_wages": e.get("passed_wages"),
            "weight": e.get("weight", 1.0),
        }
        for e in primary.eligible_employees[:50]
    ]


def min_max_anchors(mm: Any) -> list[dict[str, Any]]:
    """[H5] CALC-01 — anchoring pay periods for the Min Max denominator."""
    if mm is None:
        return []
    return [
        {
            "Employee_ID": e["Employee_ID"],
            "anchor_min_date": e["first_start"],
            "anchor_max_date": e["last_end"],
            "weeks_worked": e["weeks_worked"],
        }
        for e in mm.eligible_employees[:50]
        if "first_start" in e and "last_end" in e
    ]


def eligibility_floors(pack: Any, tax_year: int) -> dict[str, Any]:
    """[H1] The resolved year-specific floors."""
    return {
        "tax_year": tax_year,
        "min_weekly_hours": pack.min_weekly_hours,
        "min_weekly_wages": pack.min_weekly_wages,
        "wage_test_applies": pack.min_weekly_wages > 0,
        "pt_band_hours": list(pack.pt_band_hours) if pack.pt_band_hours else None,
        "pt_weight": pack.pt_weight,
        "measuring_date": pack.measuring_date,
        "entity_combination": pack.entity_combination,
    }


def reconciliation(pp: Any, mm: Any) -> dict[str, Any]:
    """The two certified methods set against each other."""
    recon = reconcile_methods(pp, mm)
    return {
        "annual_average_diff": recon.annual_average_diff,
        "unit_diff_count": sum(1 for u in recon.units if u["max_abs_diff"] > 0),
        "donut_hole_employee_count": len(recon.employee_weeks_donut_hole),
        "eligibility_disagreement_count": len(recon.eligibility_disagreements),
        "invariant_holds": recon.invariant_holds,  # [Phase C] MinMax >= 1/0
        "invariant_violation_count": len(recon.invariant_violations),
        "invariant_violations": recon.invariant_violations,
        "units": recon.units,
        "donut_hole_top_10": recon.employee_weeks_donut_hole[:10],
    }


def entity_breakdowns(primary: Any) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """[I1] per-FEIN and [L3] per-site x per-entity breakdowns, from the deduped primary matrix.

    Each FEIN is labelled with its legal-entity name so the breakdown reads as real
    companies, not bare tax IDs. GA is a per-location test and a single site can host
    several FEINs, so the credible grain is site x entity, not just one axis.
    """
    by_fein = rollup_matrix_by_field(primary.employee_unit_matrix, "Entity_FEIN")
    for fcode, agg in by_fein.items():
        agg["entity_name"] = entity_name(fcode)
    by_site = rollup_matrix_by_two_fields(primary.employee_unit_matrix, "Worksite_ID", "Entity_FEIN")
    feins_per_site: dict[str, set[str]] = {}
    for row in by_site:
        row["entity_name"] = entity_name(row["Entity_FEIN"])
        feins_per_site.setdefault(row["Worksite_ID"], set()).add(row["Entity_FEIN"])
    multi = sorted(s for s, feins in feins_per_site.items() if len(feins) > 1)
    return by_fein, by_site, multi


def _combination_note(treatment: str, entity_count: int) -> str:
    if treatment == "prohibited":
        return (
            "Entities cannot be combined for this program (DISC-4); credit is "
            "computed per FEIN with the statutory threshold applied to each, then summed."
        )
    if entity_count > 1:
        return (
            f"{entity_count} legal entities in this state; combination is "
            f"'{treatment}' (pending DISC-4), so they are tested together on the "
            "combined state Average Headcount. Under a 'prohibited' state each entity would be "
            "tested against the threshold on its own."
        )
    return (
        f"Single legal entity in this state; combination is '{treatment}' "
        "(pending DISC-4). Credit computed on the state Average Headcount."
    )


def _prohibited(state: str, fein_breakdown: dict[str, Any], credit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Per-FEIN credit with the threshold applied to each entity, then summed: `(view extras, credit)`."""
    from tools.credit_math import combine_entity_credits

    combined = combine_entity_credits(state, fein_breakdown)
    for fcode, per in combined["per_fein"].items():
        per["entity_name"] = entity_name(fcode)
    extras = {
        "per_fein": combined["per_fein"],
        "combined_annual_credit_usd": combined["combined_annual_credit_usd"],
        "combined_lifetime_credit_usd": combined["combined_lifetime_credit_usd"],
    }
    credit = {
        **credit,
        "annual_credit_usd": combined["combined_annual_credit_usd"],
        "lifetime_credit_usd": combined["combined_lifetime_credit_usd"],
        "qualifying_jobs": combined["combined_qualifying_jobs"],
        "_entity_combination": "prohibited",
    }
    return extras, credit


def entity_view_and_credit(
    state: str, pack: Any, fein_breakdown: dict[str, Any], credit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """[I2] CALC-06 — apply the pack's entity-combination treatment; returns `(view, credit)`."""
    view: dict[str, Any] = {
        "treatment": pack.entity_combination,
        "_disc_ref": "DISC-4",
        "entity_count": len(fein_breakdown),
        "entities": {fcode: entity_name(fcode) for fcode in fein_breakdown},
    }
    if pack.entity_combination == "prohibited":
        extras, credit = _prohibited(state, fein_breakdown, credit)
        view.update(extras)
    view["note"] = _combination_note(pack.entity_combination, len(fein_breakdown))
    return view, credit
