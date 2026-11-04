"""[P1] PILOT-04 — reconcile our live engine output against a benchmark.

Ties our per-state Average Headcount out against a SYNTHETIC benchmark fixture standing
in for the partner's Access/Copilot calculation. The real parallel run happens inside the
partner's environment (payroll never leaves the partner); this proves the reconciliation
machinery and surfaces any discrepancies.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from application.mediator import Query
from application.onezero_errors import OneZeroNotFound
from application.payroll_rows import iter_state_packs, require_pay_periods

_BENCHMARK = Path(__file__).resolve().parents[2] / "data" / "onezero_benchmark_synthetic.json"


@dataclass(frozen=True)
class GetReconciliationQuery(Query):
    """Reconcile the live engine against the benchmark fixture for a tax year."""

    tax_year: int
    account_id: int | None = None


def _computed_averages(rows: list[dict[str, Any]], tax_year: int, fy_end_month: int) -> list[dict[str, Any]]:
    from domain.calculation.onezero import fiscal_window_start, run_pay_period_method

    computed = []
    for st, pack, state_rows in iter_state_packs(rows, tax_year=tax_year):
        res = run_pay_period_method(
            state_rows, tax_year=tax_year,
            analysis_start_month=fiscal_window_start(tax_year, fy_end_month),
            pack=pack, fiscal_year_end_month=fy_end_month,
        )
        computed.append({"key": st, "average_headcount": res.annual_average})
    return computed


def handle_get_reconciliation(query: GetReconciliationQuery) -> dict[str, Any]:
    """The reconciliation report, with where the benchmark came from."""
    from config import get_fiscal_year_end_month
    from domain.calculation.onezero import fiscal_year_of
    from tools.reconcile import reconcile

    if not _BENCHMARK.exists():
        raise OneZeroNotFound("benchmark fixture not found")
    bench = json.loads(_BENCHMARK.read_text(encoding="utf-8"))

    fy_end_month = get_fiscal_year_end_month()
    all_rows = require_pay_periods(account_id=query.account_id)
    rows = [
        r for r in all_rows
        if fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10]), fy_end_month) == query.tax_year
    ]
    report = reconcile(
        bench.get("rows", []), _computed_averages(rows, query.tax_year, fy_end_month),
        tolerance=float(bench.get("tolerance", 0.5)),
    )
    report["benchmark_source"] = {
        "_synthetic": bench.get("_synthetic", True),
        "note": bench.get("_note"),
        "tax_year": bench.get("tax_year"),
    }
    report["tax_year"] = query.tax_year
    return report
