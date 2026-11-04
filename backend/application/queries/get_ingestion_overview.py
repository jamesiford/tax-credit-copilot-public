"""Source → canonical → QC for a tax year: how raw payroll becomes the output.

Raw BCS pay-period rows → canonical records (field map + worksite join + pay-code
classification + cash-basis trim) → QC exception report, with a human validation or
correction checkpoint on every anomaly (nothing is silently dropped). The transform
lives in `tools/canonical.py`, the QC checks in `tools/qc.py`; this read arranges what
they return and attaches the human resolutions held in `application.qc_resolutions`.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from application.mediator import Query
from application.payroll_rows import require_pay_periods
from application.qc_resolutions import QC_RESOLUTIONS, exception_id
from application.source_ports import client_fiscal_window, configured_account_id

# Source column -> canonical field (DATA-03). Shown in the UI so the transform
# is legible, not a black box.
FIELD_MAP: list[dict[str, str]] = [
    {"source": "Employee_ID", "canonical": "employee_id", "note": "surrogate key (PII-minimal)"},
    {"source": "Worksite_ID", "canonical": "worksite_id", "note": "unit granularity + worksite join (DATA-04)"},
    {"source": "Entity_FEIN", "canonical": "legal_entity_fein", "note": "legal entity / cost centre"},
    {"source": "Pay_Period_Start", "canonical": "pay_period_start", "note": "true-weeks basis"},
    {"source": "Pay_Period_End", "canonical": "pay_period_end", "note": "measuring-date anchor"},
    {"source": "Pay_Date", "canonical": "pay_date", "note": "cash-basis fiscal-year anchor (DATA-06)"},
    {"source": "Hours_Worked", "canonical": "hours_worked", "note": "weekly-hours floor input"},
    {"source": "Gross_Wages", "canonical": "gross_wages", "note": "weekly-wage floor input"},
    {"source": "Pay_Code", "canonical": "pay_code / includable", "note": "wage-basis classification (DATA-05 / CALC-11)"},
]


AUTOMATION = {
    "agents": ["PayrollIngestAgent", "ExceptionReportAgent"],
    "note": "Ingestion is agent-automated; the numbers below are deterministic. "
            "The human validates exceptions and corrections — the agent never drops a record.",
}


@dataclass(frozen=True)
class GetIngestionOverviewQuery(Query):
    """Source → canonical → QC for a tax year (default GA)."""

    tax_year: int
    state: str = "GA"
    account_id: int | None = None


def _fiscal_window_for(account_id: int | None, tax_year: int, program: str):
    """The client's fiscal window, or None when no rule or statute resolves.

    `account_id` is normalised first: naming the default tenant explicitly and
    leaving it implicit must resolve the same window, or this screen contradicts
    itself depending on how the caller addressed it.
    """
    from tools.credit_math import resolve_tax_year_convention

    try:
        convention = resolve_tax_year_convention(program, tax_year)
        return client_fiscal_window(
            account_id if account_id is not None else configured_account_id(),
            tax_year,
            convention["label"],
        )
    except (FileNotFoundError, ValueError, KeyError):
        return None


def _raw_sample(state_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Raw source sample (state-scoped) — shows Tax_Year vs Pay_Date so the cash-basis trim is visible."""
    return [
        {
            "Employee_ID": r.get("Employee_ID"),
            "Worksite_ID": r.get("Worksite_ID"),
            "Entity_FEIN": r.get("Entity_FEIN"),
            "Pay_Period_Start": r.get("Pay_Period_Start"),
            "Pay_Period_End": r.get("Pay_Period_End"),
            "Pay_Date": r.get("Pay_Date"),
            "Tax_Year": r.get("Tax_Year"),
            "Hours_Worked": r.get("Hours_Worked"),
            "Gross_Wages": r.get("Gross_Wages"),
            "Pay_Code": r.get("Pay_Code", "Regular"),
        }
        for r in state_rows[:12]
    ]


def _fiscal_selection(
    all_rows: list[dict[str, Any]], state_rows: list[dict[str, Any]], prefix: str, window: Any, tax_year: int,
) -> tuple[list[dict[str, Any]], str]:
    """The rows the run selected, and the sentence that says how.

    The run selects by the client's FISCAL WINDOW, so that is what this screen
    counts. `to_canonical`'s calendar-year trim is display-only — nothing
    statutory reads it — and showing it here claimed a selection the engine
    never made: 155,293 rows for a client whose run used 384,418.
    """
    if window is None:
        return all_rows, f"no fiscal rule resolved for {tax_year}; all rows carried forward"
    begin, end = window.begin.isoformat(), window.end.isoformat()
    selected = [r for r in all_rows if begin <= str(r.get("Pay_Date") or "")[:10] <= end]
    dropped = len(state_rows) - len([r for r in selected if str(r.get("Worksite_ID", "")).startswith(prefix)])
    return selected, (
        f"{window.begin} to {window.end}, read from the client's own fiscal rule; "
        f"{dropped} excluded because the paycheck fell outside the fiscal year"
    )


def _exceptions(all_rows: list[dict[str, Any]], tax_year: int, st: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The QC report, with human resolutions attached and friendly worksite labels."""
    from data.sites import worksite_name
    from tools.qc import run_exception_report

    qc = run_exception_report(all_rows, tax_year=tax_year, state=st)
    exceptions: list[dict[str, Any]] = []
    for anomaly in qc["test_of_twos"] + qc["meaningful_pay_period"]:
        eid = exception_id(anomaly)
        enriched = {**anomaly, "exception_id": eid, "resolution": QC_RESOLUTIONS.get(eid)}
        if enriched.get("units"):
            enriched["units"] = [
                {**u, "worksite_name": worksite_name(u.get("worksite_id"))} for u in enriched["units"]
            ]
        if enriched.get("worksite_id"):
            enriched["worksite_name"] = worksite_name(enriched["worksite_id"])
        exceptions.append(enriched)
    return qc, exceptions


def _pipeline(state_rows: list, recs: list, includable: list, periods: list, st: str, note: str) -> list[dict[str, Any]]:
    return [
        {"stage": "Source rows (all years)", "count": len(state_rows),
         "note": f"raw BCS pay-period rows for {st}"},
        {"stage": "Selected by fiscal window (BA-01)", "count": len(recs), "note": note},
        {"stage": "Includable after pay-code filter (DATA-05)", "count": len(includable),
         "note": f"{len(recs) - len(includable)} non-wage lines suppressed (mileage / reimbursement)"},
        {"stage": "Collapsed to employee×pay-period", "count": len(periods),
         "note": "one record per employee per pay period"},
    ]


def _totals(state_rows: list, recs: list, includable: list, periods: list) -> dict[str, int]:
    return {
        "source_rows": len(state_rows),
        "fiscal_year_rows": len(recs),
        "includable_rows": len(includable),
        "excluded_rows": len(recs) - len(includable),
        "employee_periods": len(periods),
        "distinct_employees": len({r.employee_id for r in recs}),
        "distinct_worksites": len({r.worksite_id for r in recs}),
    }


def _canonical_records(selected_rows: list[dict[str, Any]], program: str, prefix: str) -> list[Any]:
    from tools.canonical import RowsAdapter, to_canonical

    return [r for r in to_canonical(RowsAdapter(selected_rows), program=program) if r.worksite_id.startswith(prefix)]


def handle_get_ingestion_overview(query: GetIngestionOverviewQuery) -> dict[str, Any]:
    """The raw sample, the field map, the stage counts, the pay-code split and the QC report."""
    from tools.canonical import collapse_to_employee_period

    st = query.state.upper()
    pref = f"{st}_"
    all_rows = require_pay_periods(account_id=query.account_id)
    state_rows = [r for r in all_rows if str(r.get("Worksite_ID", "")).startswith(pref)]

    program = "GA_JTC" if st == "GA" else f"{st}_JTC"
    window = _fiscal_window_for(query.account_id, query.tax_year, program)
    selected_rows, selection_note = _fiscal_selection(all_rows, state_rows, pref, window, query.tax_year)

    recs = _canonical_records(selected_rows, program, pref)
    includable = [r for r in recs if r.includable]
    periods = collapse_to_employee_period(recs)
    qc, exceptions = _exceptions(all_rows, query.tax_year, st)
    unresolved = sum(1 for e in exceptions if e["resolution"] is None)

    return {
        "as_of": date.today().isoformat(),
        "tax_year": query.tax_year,
        "state": st,
        "automation": AUTOMATION,
        "field_map": FIELD_MAP,
        "raw_sample": _raw_sample(state_rows),
        "pipeline": _pipeline(state_rows, recs, includable, periods, st, selection_note),
        "totals": _totals(state_rows, recs, includable, periods),
        "pay_code_split": [
            {"pay_code": k, "count": v} for k, v in sorted(Counter(r.pay_code for r in recs).items())
        ],
        "qc": {
            "summary": {**qc["summary"], "unresolved": unresolved},
            "thresholds": qc["thresholds"],
            "exceptions": exceptions,
        },
    }
