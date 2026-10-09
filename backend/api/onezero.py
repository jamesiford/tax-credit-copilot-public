"""One/Zero statutory engine endpoints.

The June-4 (ROADMAP-II) hot domain, extracted from the former monolithic
`api/eligibility.py`. Everything here runs the statutory Base Calculation
(per the partner's BCS spec) over the BCS-shaped pay-period CSV:

  GET  /api/onezero/{tax_year}        — both methods + reconciliation + [H1..I2]
  GET  /api/onezero/retroactive/scan  — replay across prior tax years
  GET  /api/triggers                  — the partner's 4 opportunity flags
  GET  /api/performance/{tax_year}    — green/yellow/red headroom against the floors
  GET  /api/alerts/monthly/{tax_year} — [J3] monthly cadence + per-employee levers
  POST /api/simulate/onezero          — [J2] entity-level statutory simulator

Loading + per-state-pack iteration is shared via `api._payperiods`; the
entity-combination math and simulator row-mutation live in the tool layer
(`tools.credit_math` / `tools.simulation`).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Query as FastAPIQuery
from pydantic import BaseModel, Field

from data.claims import get_all_claims
from api._payperiods import (
    iter_state_packs,
    require_pay_periods,
    row_state,
    unauthored_state_years,
)

router = APIRouter(prefix="/api", tags=["onezero"])


@router.get("/onezero/matrix/{tax_year}")
def onezero_matrix(
    tax_year: int,
    state: str = FastAPIQuery("GA", description="Two-letter state code"),
    account_id: int | None = FastAPIQuery(None, description="Client; defaults to the tenant"),
    method: str = FastAPIQuery("min_max", description="min_max | pay_period"),
) -> dict[str, Any]:
    """The monthly one/zero allocation for one client, at unit x legal entity.

    Thin [ADR-003]: the resolution and the run live in the application layer.
    The older `/onezero/{tax_year}` below buckets rows by a global fiscal-year
    end month; this one resolves the window from the client's own rules, so it
    agrees with `/api/eligibility/{tax_year}` for the same client and year.
    """
    from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery
    from application.queries._client_run import ClientRunNotAvailable
    from application.wiring import get_mediator

    try:
        query = GetOneZeroMatrixQuery(
            tax_year=tax_year, state=state, account_id=account_id, method=method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(query)
    except ClientRunNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc




@router.get("/onezero/{tax_year}")
def one_zero(
    tax_year: int,
    state: str | None = None,
    method: str = "both",
    fein: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """Run the statutory One/Zero Base Calculation for a given tax year.

    Query params:
      `state`  (optional): two-letter state code. If omitted, every pack runs.
      `method` (optional): [H5] CALC-01/02 — 'pay_period' | 'min_max' | 'both'.
      `fein`   (optional): [I1] CALC-06 — restrict to a single legal entity.
      `account_id` (optional): which tenant to calculate. Omitted keeps the
        configured default, so existing single-tenant callers are unchanged.
    """
    from domain.calculation.onezero import (
        run_pay_period_method, run_min_max_method, reconcile_methods,
        rollup_matrix_by_field, rollup_matrix_by_two_fields, fiscal_window_start, fiscal_year_of,
    )
    from tools.credit_math import (
        load_pack_one_zero, apply_one_zero_state_credit, combine_entity_credits,
    )
    from config import get_fiscal_year_end_month

    method = (method or "both").lower()
    if method not in ("pay_period", "min_max", "both"):
        raise HTTPException(status_code=400, detail="method must be pay_period | min_max | both")

    fy_end_month = get_fiscal_year_end_month()  # [H4] CALC-05
    all_rows = require_pay_periods(drop_qc=True, account_id=account_id)

    # [H4] Bucket rows into the configured fiscal year by PAY DATE.
    def _fy(row: dict[str, Any]) -> int:
        return fiscal_year_of(date.fromisoformat(str(row["Pay_Date"])[:10]), fy_end_month)

    rows = [r for r in all_rows if _fy(r) == tax_year]
    prior_rows = [r for r in all_rows if _fy(r) == tax_year - 1]
    if fein:
        rows = [r for r in rows if r.get("Entity_FEIN") == fein]
        prior_rows = [r for r in prior_rows if r.get("Entity_FEIN") == fein]

    results_by_state: list[dict[str, Any]] = []
    for st, pack, state_rows in iter_state_packs(rows, tax_year=tax_year, state=state):
        analysis_start = fiscal_window_start(tax_year, fy_end_month)  # [H4]

        # [L4] CALC-10 — prefer a NEGOTIATED wage standard + minimum over the
        # statutory pack values when an incentive agreement is on file. Applied
        # BEFORE the run so the negotiated wage floor drives eligibility.
        from tools.negotiated import resolve_override
        import dataclasses
        override = resolve_override(st)
        threshold_override = None
        if override:
            if override.get("wage_standard_weekly") is not None:
                pack = dataclasses.replace(pack, min_weekly_wages=float(override["wage_standard_weekly"]))
            if override.get("min_jobs") is not None:
                threshold_override = float(override["min_jobs"])

        pp = mm = None
        if method in ("pay_period", "both"):
            pp = run_pay_period_method(
                state_rows, tax_year=tax_year, analysis_start_month=analysis_start,
                pack=pack, fiscal_year_end_month=fy_end_month,
            )
        if method in ("min_max", "both"):
            mm = run_min_max_method(
                state_rows, tax_year=tax_year, analysis_start_month=analysis_start,
                pack=pack, fiscal_year_end_month=fy_end_month,
            )
        primary = pp or mm  # pay_period preferred for the headline figures

        # [H3] CALC-04 — year-over-year Average Headcount delta.
        prior_state_rows = [r for r in prior_rows if r["Worksite_ID"].startswith(f"{st}_")]
        prior_avg = 0.0
        if prior_state_rows:
            prior_pack = load_pack_one_zero(st, tax_year=tax_year - 1)
            if prior_pack is not None:
                prior_start = fiscal_window_start(tax_year - 1, fy_end_month)
                runner = run_min_max_method if method == "min_max" else run_pay_period_method
                prior_res = runner(
                    prior_state_rows, tax_year=tax_year - 1, analysis_start_month=prior_start,
                    pack=prior_pack, fiscal_year_end_month=fy_end_month,
                )
                prior_avg = prior_res.annual_average

        # [Net-new] Credit is computed on the YEAR-OVER-YEAR delta in Average
        # Headcount (the state packs are net-new-jobs credits). prior_avg is 0
        # for an establishment year / brand-new state with no prior-year rows,
        # so its full headcount counts — which is correct for a first claim.
        credit = apply_one_zero_state_credit(st, primary.annual_average, prior_period_average_headcount=prior_avg, threshold_override=threshold_override)

        # [H1] CALC-03 — per-employee eligibility test outcomes for audit.
        eligibility_sample = [
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
        part_time_count = sum(1 for e in primary.eligible_employees if e.get("weight", 1.0) < 1.0)

        # [I1] CALC-06 — per-FEIN breakdown from the (deduped) primary matrix.
        fein_breakdown = rollup_matrix_by_field(primary.employee_unit_matrix, "Entity_FEIN")
        # Label each FEIN with its legal-entity name so the breakdown reads as
        # real companies (e.g. the Savannah DC subsidiary) not bare tax IDs.
        from data.entities import entity_name
        for fcode, agg in fein_breakdown.items():
            agg["entity_name"] = entity_name(fcode)

        # [L3] CALC-09 — per-SITE × per-LEGAL-ENTITY drill. GA is a per-location
        # test and a single site can host multiple FEINs, so the credible grain
        # is site × entity, not just one axis.
        site_entity_breakdown = rollup_matrix_by_two_fields(
            primary.employee_unit_matrix, "Worksite_ID", "Entity_FEIN",
        )
        for row in site_entity_breakdown:
            row["entity_name"] = entity_name(row["Entity_FEIN"])
        _feins_per_site: dict[str, set[str]] = {}
        for row in site_entity_breakdown:
            _feins_per_site.setdefault(row["Worksite_ID"], set()).add(row["Entity_FEIN"])
        multi_entity_sites = sorted(s for s, feins in _feins_per_site.items() if len(feins) > 1)


        # [I2] CALC-06 — apply the pack's entity-combination treatment.
        entity_view: dict[str, Any] = {
            "treatment": pack.entity_combination,
            "_disc_ref": "DISC-4",
            "entity_count": len(fein_breakdown),
            "entities": {fcode: entity_name(fcode) for fcode in fein_breakdown},
        }
        if pack.entity_combination == "prohibited":
            combined = combine_entity_credits(st, fein_breakdown)
            for fcode, per in combined["per_fein"].items():
                per["entity_name"] = entity_name(fcode)
            entity_view["per_fein"] = combined["per_fein"]
            entity_view["combined_annual_credit_usd"] = combined["combined_annual_credit_usd"]
            entity_view["combined_lifetime_credit_usd"] = combined["combined_lifetime_credit_usd"]
            entity_view["note"] = (
                "Entities cannot be combined for this program (DISC-4); credit is "
                "computed per FEIN with the statutory threshold applied to each, then summed."
            )
            credit = {
                **credit,
                "annual_credit_usd": combined["combined_annual_credit_usd"],
                "lifetime_credit_usd": combined["combined_lifetime_credit_usd"],
                "qualifying_jobs": combined["combined_qualifying_jobs"],
                "_entity_combination": "prohibited",
            }
        elif len(fein_breakdown) > 1:
            entity_view["note"] = (
                f"{len(fein_breakdown)} legal entities in this state; combination is "
                f"'{pack.entity_combination}' (pending DISC-4), so they are tested together on the "
                "combined state Average Headcount. Under a 'prohibited' state each entity would be "
                "tested against the threshold on its own."
            )
        else:
            entity_view["note"] = (
                f"Single legal entity in this state; combination is '{pack.entity_combination}' "
                "(pending DISC-4). Credit computed on the state Average Headcount."
            )

        # [H5] CALC-01 — anchoring pay periods for the Min Max denominator.
        min_max_anchors = []
        if mm is not None:
            for e in mm.eligible_employees[:50]:
                if "first_start" in e and "last_end" in e:
                    min_max_anchors.append({
                        "Employee_ID": e["Employee_ID"],
                        "anchor_min_date": e["first_start"],
                        "anchor_max_date": e["last_end"],
                        "weeks_worked": e["weeks_worked"],
                    })

        entry: dict[str, Any] = {
            "state": st,
            "rule_pack_citation": pack.citation,
            "method": method,
            "eligibility_floors": {  # [H1] resolved year-specific floors
                "tax_year": tax_year,
                "min_weekly_hours": pack.min_weekly_hours,
                "min_weekly_wages": pack.min_weekly_wages,
                "wage_test_applies": pack.min_weekly_wages > 0,
                "pt_band_hours": list(pack.pt_band_hours) if pack.pt_band_hours else None,
                "pt_weight": pack.pt_weight,
                "measuring_date": pack.measuring_date,
                "entity_combination": pack.entity_combination,
            },
            "negotiated_override": override,  # [L4] CALC-10 (None unless on file)
            "eligible_employee_count": len(primary.eligible_employees),
            "part_time_eligible_count": part_time_count,  # [H2]
            "eligibility_sample": eligibility_sample,      # [H1]
            "pay_period_summary": pp.summary if pp else [],
            "min_max_summary": mm.summary if mm else [],
            "pay_period_average_headcount": pp.annual_average if pp else 0.0,
            "min_max_average_headcount": mm.annual_average if mm else 0.0,
            "average_headcount": primary.annual_average,
            "prior_year_average_headcount": prior_avg,     # [H3]
            "yoy_delta": round(primary.annual_average - prior_avg, 2),  # [H3]
            "fein_breakdown": fein_breakdown,              # [I1]
            "site_entity_breakdown": site_entity_breakdown,  # [L3]
            "multi_entity_sites": multi_entity_sites,        # [L3]
            "entity_combination_view": entity_view,        # [I2]
            "min_max_anchors": min_max_anchors,            # [H5]
            "credit_estimate": credit,
            "data_quality_flags": (pp.flags if pp else []) + (mm.flags if mm else []),
            "_roadmap_tag": ["H1", "H2", "H3", "H5", "I1", "I2", "L3", "L4"],
        }
        if pp and mm:
            recon = reconcile_methods(pp, mm)
            entry["reconciliation"] = {
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
        results_by_state.append(entry)

    return {
        "as_of": date.today().isoformat(),
        "tax_year": tax_year,
        "method": method,
        "fein": fein,
        "fiscal_year_end_month": fy_end_month,  # [H4] CALC-05
        "method_docs": [
            "the Pay Period Method (preferred)",
            "the Min Max Method (fallback)",
            "the BCS business-framing overview",
        ],
        "row_count": len(rows),
        "state_count": len(results_by_state),
        "results": results_by_state,
    }


# ---------------------------------------------------------------------------
# Per-employee derivation drill + human validation annotations (Stage 2)
# ---------------------------------------------------------------------------

_EMPLOYEE_REVIEWS: dict[str, dict[str, Any]] = {}


def reset_employee_reviews() -> None:
    """Test hook — clear the in-memory employee-review annotations."""
    _EMPLOYEE_REVIEWS.clear()


class EmployeeReviewRequest(BaseModel):
    """Human validation/correction annotation for one employee's eligibility."""
    status: str = Field("validated", pattern="^(validated|flagged|cleared)$")
    note: str | None = None
    reviewer: str = "Reviewer"


@router.get("/onezero/{tax_year}/employee/{employee_id}")
def one_zero_employee(
    tax_year: int,
    employee_id: str,
    state: str = "GA",
    account_id: int | None = None,
) -> dict[str, Any]:
    """Per-employee derivation drill: source pay-period lines → weekly averages
    → floor test (hours & wages) → weight (1 / pt_weight / 0) → per-month
    contribution → contribution to Average Headcount. A faithful slice of the
    statutory engine — it can never disagree with the headline number.
    """
    from domain.calculation.onezero import employee_derivation, fiscal_window_start, fiscal_year_of
    from tools.credit_math import load_pack_one_zero
    from config import get_fiscal_year_end_month

    pack = load_pack_one_zero(state, tax_year=tax_year)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"No rule pack for state {state}")

    fy_end_month = get_fiscal_year_end_month()
    all_rows = require_pay_periods(drop_qc=True, account_id=account_id)

    def _fy(row: dict[str, Any]) -> int:
        return fiscal_year_of(date.fromisoformat(str(row["Pay_Date"])[:10]), fy_end_month)

    pref = f"{state.upper()}_"
    rows = [
        r for r in all_rows
        if _fy(r) == tax_year and str(r.get("Worksite_ID", "")).startswith(pref)
    ]

    # Parity with /api/onezero: prefer a negotiated wage standard when on file.
    from tools.negotiated import resolve_override
    import dataclasses
    override = resolve_override(state.upper())
    if override and override.get("wage_standard_weekly") is not None:
        pack = dataclasses.replace(pack, min_weekly_wages=float(override["wage_standard_weekly"]))

    detail = employee_derivation(
        rows, employee_id=employee_id, tax_year=tax_year,
        analysis_start_month=fiscal_window_start(tax_year, fy_end_month),
        pack=pack, fiscal_year_end_month=fy_end_month,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pay-period rows for {employee_id} in {state.upper()} {tax_year}",
        )
    detail["state"] = state.upper()
    detail["review"] = _EMPLOYEE_REVIEWS.get(employee_id)
    from data.sites import worksite_name
    for ln in detail.get("source_lines", []):
        ln["Worksite_Name"] = worksite_name(ln.get("Worksite_ID"))
    for m in detail.get("months", []):
        if m.get("worksite_id"):
            m["worksite_name"] = worksite_name(m["worksite_id"])
    return detail


@router.post("/onezero/employee/{employee_id}/review")
def review_employee(employee_id: str, req: EmployeeReviewRequest) -> dict[str, Any]:
    """Record a human validation/correction annotation for an employee
    (in-memory; resets on restart — prod persists to the audit store)."""
    if req.status == "cleared":
        _EMPLOYEE_REVIEWS.pop(employee_id, None)
        return {"ok": True, "review": None}
    entry = {
        "employee_id": employee_id,
        "status": req.status,
        "note": req.note,
        "reviewer": req.reviewer,
        "reviewed_at": date.today().isoformat(),
    }
    _EMPLOYEE_REVIEWS[employee_id] = entry
    return {"ok": True, "review": entry}








@router.get("/designations/{state}")
def designations(state: str, tax_year: int = 2025) -> dict[str, Any]:
    """[L2] CALC-08 — designation timelines + parallel-calc flags for a state.
    Surfaces which GA locations changed designation between the base year and
    the analysis year (a change that, combined with net-new jobs, spawns two
    concurrent calcs for the same location).
    """
    from tools.designation import detect_designation_splits
    return detect_designation_splits(state, tax_year)


@router.get("/reconcile/{tax_year}")
def reconcile_endpoint(tax_year: int, account_id: int | None = None) -> dict[str, Any]:
    """[P1] PILOT-04 — reconcile our live engine output against a benchmark.

    Ties our per-state Average Headcount out against a SYNTHETIC benchmark
    fixture standing in for the partner's Access/Copilot calc. The real parallel run
    happens inside the partner's environment (payroll never leaves the partner);
    this proves the reconciliation machinery and surfaces any discrepancies.
    """
    import json
    from pathlib import Path
    from domain.calculation.onezero import run_pay_period_method, fiscal_window_start, fiscal_year_of
    from tools.reconcile import reconcile
    from config import get_fiscal_year_end_month

    bench_path = Path(__file__).resolve().parent.parent / "data" / "onezero_benchmark_synthetic.json"
    if not bench_path.exists():
        raise HTTPException(status_code=404, detail="benchmark fixture not found")
    bench = json.loads(bench_path.read_text(encoding="utf-8"))

    fy_end_month = get_fiscal_year_end_month()
    all_rows = require_pay_periods(account_id=account_id)

    def _fy(row: dict[str, Any]) -> int:
        return fiscal_year_of(date.fromisoformat(str(row["Pay_Date"])[:10]), fy_end_month)

    rows = [r for r in all_rows if _fy(r) == tax_year]
    computed: list[dict[str, Any]] = []
    for st, pack, state_rows in iter_state_packs(rows, tax_year=tax_year):
        res = run_pay_period_method(
            state_rows, tax_year=tax_year,
            analysis_start_month=fiscal_window_start(tax_year, fy_end_month),
            pack=pack, fiscal_year_end_month=fy_end_month,
        )
        computed.append({"key": st, "average_headcount": res.annual_average})

    report = reconcile(
        bench.get("rows", []), computed,
        tolerance=float(bench.get("tolerance", 0.5)),
    )
    report["benchmark_source"] = {
        "_synthetic": bench.get("_synthetic", True),
        "note": bench.get("_note"),
        "tax_year": bench.get("tax_year"),
    }
    report["tax_year"] = tax_year
    return report




















@router.get("/qc/{tax_year}")
def qc_exception_report(
    tax_year: int,
    state: str | None = None,
    min_wages: float = 50.0,
    min_hours: float = 4.0,
    account_id: int | None = None,
) -> dict[str, Any]:
    """[B5 / CALC-07 + CALC-08 / AI-02] Automated QC exception report.

    Surfaces the "2s" (an employee counted at >1 unit in a month) and scraggly
    low-value pay periods for human review. Nothing is dropped automatically —
    every anomaly is a validation checkpoint.
    """
    from tools.qc import run_exception_report

    rows = require_pay_periods(account_id=account_id)
    return run_exception_report(
        rows, tax_year=tax_year, state=state, min_wages=min_wages, min_hours=min_hours
    )
