"""[B5 / CALC-07 + CALC-08 / AI-02] Automated QC exception report.

Surfaces the "2s" (an employee counted at >1 unit in a month) and scraggly low-value
pay periods for human review. Nothing is dropped automatically — every anomaly is a
validation checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.payroll_rows import require_pay_periods


@dataclass(frozen=True)
class GetQcExceptionReportQuery(Query):
    """The QC exception report for a tax year; the thresholds decide what counts as scraggly."""

    tax_year: int
    state: str | None = None
    min_wages: float = 50.0
    min_hours: float = 4.0
    account_id: int | None = None


def handle_get_qc_exception_report(query: GetQcExceptionReportQuery) -> dict[str, Any]:
    from tools.qc import run_exception_report

    rows = require_pay_periods(account_id=query.account_id)
    return run_exception_report(
        rows, tax_year=query.tax_year, state=query.state,
        min_wages=query.min_wages, min_hours=query.min_hours,
    )
