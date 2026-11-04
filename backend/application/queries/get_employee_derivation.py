"""One employee's eligibility derivation: source lines to weekly averages to the floor test.

Source pay-period lines → weekly averages → floor test (hours and wages) → weight
(1 / pt_weight / 0) → per-month contribution → contribution to Average Headcount. A
faithful slice of the statutory engine, so it can never disagree with the headline
number; it also carries any human review annotation recorded against the employee.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application import onezero_entry as entry
from application.employee_reviews import EMPLOYEE_REVIEWS
from application.mediator import Query
from application.onezero_errors import OneZeroNotFound
from application.payroll_rows import require_pay_periods


@dataclass(frozen=True)
class GetEmployeeDerivationQuery(Query):
    """The derivation for `employee_id` in `state` for `tax_year`."""

    tax_year: int
    employee_id: str
    state: str = "GA"
    account_id: int | None = None


def _state_year_rows(query: GetEmployeeDerivationQuery, fy_end_month: int) -> list[dict[str, Any]]:
    from domain.calculation.onezero import fiscal_year_of

    all_rows = require_pay_periods(drop_qc=True, account_id=query.account_id)
    prefix = f"{query.state.upper()}_"
    return [
        r for r in all_rows
        if fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month) == query.tax_year
        and str(r.get("Worksite_ID", "")).startswith(prefix)
    ]


def _name_worksites(detail: dict[str, Any]) -> None:
    from data.sites import worksite_name

    for line in detail.get("source_lines", []):
        line["Worksite_Name"] = worksite_name(line.get("Worksite_ID"))
    for month in detail.get("months", []):
        if month.get("worksite_id"):
            month["worksite_name"] = worksite_name(month["worksite_id"])


def handle_get_employee_derivation(query: GetEmployeeDerivationQuery) -> dict[str, Any]:
    """The derivation, or `OneZeroNotFound` when there is no rule pack or no rows for the employee."""
    from config import get_fiscal_year_end_month
    from domain.calculation.onezero import employee_derivation, fiscal_window_start
    from tools.credit_math import load_pack_one_zero

    pack = load_pack_one_zero(query.state, tax_year=query.tax_year)
    if pack is None:
        raise OneZeroNotFound(f"No rule pack for state {query.state}")

    fy_end_month = get_fiscal_year_end_month()
    rows = _state_year_rows(query, fy_end_month)
    # Parity with /api/onezero: prefer a negotiated wage standard when on file.
    pack, _, _ = entry.apply_negotiated_override(query.state.upper(), pack)

    detail = employee_derivation(
        rows, employee_id=query.employee_id, tax_year=query.tax_year,
        analysis_start_month=fiscal_window_start(query.tax_year, fy_end_month),
        pack=pack, fiscal_year_end_month=fy_end_month,
    )
    if detail is None:
        raise OneZeroNotFound(
            f"No pay-period rows for {query.employee_id} in {query.state.upper()} {query.tax_year}"
        )
    detail["state"] = query.state.upper()
    detail["review"] = EMPLOYEE_REVIEWS.get(query.employee_id)
    _name_worksites(detail)
    return detail
