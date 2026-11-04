"""The statutory One/Zero Base Calculation for a tax year, both methods, per state.

`GET /api/onezero/{tax_year}`. Runs the statutory engine over the BCS-shaped pay-period
rows, bucketed by the configured fiscal-year end month (the older path; the per-client
matrix resolves the client's own window instead). The report is the engine's own figures
arranged for audit: eligibility samples, the entity-combination view, the Min Max anchors
and the reconciliation of the two methods. Nothing here is a second implementation of
the calculation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application import onezero_entry as entry
from application.mediator import Query
from application.payroll_rows import iter_state_packs, require_pay_periods

_METHODS = ("pay_period", "min_max", "both")


class InvalidOneZeroMethod(ValueError):
    """`method` is not one the engine runs."""


@dataclass(frozen=True)
class GetOneZeroQuery(Query):
    """Run the One/Zero calculation for a tax year.

    `state` omitted runs every pack; `fein` restricts to one legal entity [I1];
    `account_id` omitted keeps the configured default tenant.
    """

    tax_year: int
    state: str | None = None
    method: str = "both"
    fein: str | None = None
    account_id: int | None = None

    def __post_init__(self) -> None:
        method = (self.method or "both").lower()
        if method not in _METHODS:
            raise InvalidOneZeroMethod("method must be pay_period | min_max | both")
        object.__setattr__(self, "method", method)


def _year_rows(
    all_rows: list[dict[str, Any]], tax_year: int, fy_end_month: int, fein: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(rows, prior_rows)` bucketed into the configured fiscal year by PAY DATE [H4]."""
    from domain.calculation.onezero import fiscal_year_of

    def fiscal_year(row: dict[str, Any]) -> int:
        return fiscal_year_of(date.fromisoformat(str(row["Pay_Date"])[:10]), fy_end_month)

    rows = [r for r in all_rows if fiscal_year(r) == tax_year]
    prior = [r for r in all_rows if fiscal_year(r) == tax_year - 1]
    if fein:
        rows = [r for r in rows if r.get("Entity_FEIN") == fein]
        prior = [r for r in prior if r.get("Entity_FEIN") == fein]
    return rows, prior


def _state_entry(
    st: str, pack: Any, state_rows: list[dict[str, Any]], prior_rows: list[dict[str, Any]],
    *, tax_year: int, method: str, fy_end_month: int,
) -> dict[str, Any]:
    from tools.credit_math import apply_one_zero_state_credit

    pack, threshold_override, override = entry.apply_negotiated_override(st, pack)
    pp, mm = entry.run_methods(state_rows, tax_year=tax_year, pack=pack, method=method, fy_end_month=fy_end_month)
    primary = pp or mm  # pay_period preferred for the headline figures
    prior_avg = entry.prior_year_average(prior_rows, st, tax_year=tax_year, method=method, fy_end_month=fy_end_month)
    # [Net-new] Credit is computed on the YEAR-OVER-YEAR delta in Average Headcount.
    credit = apply_one_zero_state_credit(
        st, primary.annual_average, prior_period_average_headcount=prior_avg, threshold_override=threshold_override,
    )
    by_fein, by_site, multi_entity_sites = entry.entity_breakdowns(primary)
    entity_view, credit = entry.entity_view_and_credit(st, pack, by_fein, credit)

    result: dict[str, Any] = {
        "state": st,
        "rule_pack_citation": pack.citation,
        "method": method,
        "eligibility_floors": entry.eligibility_floors(pack, tax_year),
        "negotiated_override": override,  # [L4] CALC-10 (None unless on file)
        **entry.headcount_figures(pp, mm, primary, prior_avg),
        "fein_breakdown": by_fein,  # [I1]
        "site_entity_breakdown": by_site,  # [L3]
        "multi_entity_sites": multi_entity_sites,  # [L3]
        "entity_combination_view": entity_view,  # [I2]
        "min_max_anchors": entry.min_max_anchors(mm),  # [H5]
        "credit_estimate": credit,
        "data_quality_flags": entry.quality_flags(pp, mm),
        "_roadmap_tag": list(entry.ROADMAP_TAGS),
    }
    if pp and mm:
        result["reconciliation"] = entry.reconciliation(pp, mm)
    return result


def handle_get_one_zero(query: GetOneZeroQuery) -> dict[str, Any]:
    """One entry per state that has a rule pack and rows, under the configured fiscal year."""
    from config import get_fiscal_year_end_month

    fy_end_month = get_fiscal_year_end_month()  # [H4] CALC-05
    all_rows = require_pay_periods(drop_qc=True, account_id=query.account_id)
    rows, prior_rows = _year_rows(all_rows, query.tax_year, fy_end_month, query.fein)
    results = [
        _state_entry(
            st, pack, state_rows, prior_rows,
            tax_year=query.tax_year, method=query.method, fy_end_month=fy_end_month,
        )
        for st, pack, state_rows in iter_state_packs(rows, tax_year=query.tax_year, state=query.state)
    ]
    return {
        "as_of": date.today().isoformat(),
        "tax_year": query.tax_year,
        "method": query.method,
        "fein": query.fein,
        "fiscal_year_end_month": fy_end_month,  # [H4] CALC-05
        "method_docs": [
            "the Pay Period Method (preferred)",
            "the Min Max Method (fallback)",
            "the BCS business-framing overview",
        ],
        "row_count": len(rows),
        "state_count": len(results),
        "results": results,
    }
