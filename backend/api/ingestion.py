"""Data Ingestion endpoints (Stage 1 — the automated ingest surface).

Shows *how the source becomes the output*: raw BCS pay-period rows → canonical
records (field map + worksite join + pay-code classification + cash-basis trim)
→ QC exception report — with a human validation/correction checkpoint on every
anomaly (nothing is silently dropped).

  GET  /api/ingestion/{tax_year}                              — source → canonical → QC
  POST /api/ingestion/{tax_year}/exceptions/{exception_id}/resolve — human resolution

The transform lives in `tools/canonical.py`; the QC checks in `tools/qc.py`.
This router only orchestrates + owns the in-memory resolution store (resets on
restart — prod persists to the audit store).
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api._payperiods import require_pay_periods
from data.sites import worksite_name

router = APIRouter(prefix="/api", tags=["ingestion"])

# Source column -> canonical field (DATA-03). Shown in the UI so the transform
# is legible, not a black box.
_FIELD_MAP: list[dict[str, str]] = [
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

# In-memory human resolutions of QC exceptions (resets on restart).
_QC_RESOLUTIONS: dict[str, dict[str, Any]] = {}


def reset_qc_resolutions() -> None:
    """Test hook — clear the in-memory QC resolution store."""
    _QC_RESOLUTIONS.clear()


def _exception_id(anomaly: dict[str, Any]) -> str:
    """Deterministic id so a resolution sticks to the same anomaly across reloads.

    A scraggly period is keyed by its payroll LINE (`tools.qc.pay_line_keys`),
    not by (employee, worksite, pay_date): several lines share that triple, and
    keying on it gave them one id, so resolving one resolved all of them.
    """
    if anomaly.get("type") == "test_of_twos":
        return f"t2:{anomaly.get('employee_id')}:{anomaly.get('month')}"
    return f"pp:{anomaly.get('line_key')}"


def apply_calc_drops(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter pay-period rows per the human QC resolutions so a resolved exception
    actually flows into the calculation (option-b correction loop).

    * **test-of-twos** resolved `assign` with `keep_worksite=W` → for that
      (employee, month) the rows at every OTHER unit are dropped, so the head is
      no longer double-counted across units (the engine only dedupes per-unit).
    * **scraggly period** resolved `drop` → that one payroll LINE is removed.
      Other lines paid to the same person at the same site on the same day
      stay; dropping them too would remove wages nobody flagged.

    `accept` / `flag` are annotations — they never change the rows. Applied only
    to the CALC row-sets (see `require_pay_periods(drop_qc=True)`), never to the
    QC detector, so a resolved exception still lists with its status.
    """
    if not _QC_RESOLUTIONS:
        return rows
    t2_keep: dict[tuple[str, str], str] = {}   # (employee, YYYY-MM) -> keep worksite
    pp_drop: set[str] = set()                  # payroll line keys
    for eid, res in _QC_RESOLUTIONS.items():
        parts = eid.split(":")
        if eid.startswith("t2:") and res.get("resolution") == "assign" and res.get("keep_worksite"):
            if len(parts) >= 3:
                t2_keep[(parts[1], parts[2])] = res["keep_worksite"]
        elif eid.startswith("pp:") and res.get("resolution") == "drop":
            pp_drop.add(eid[3:])
    if not t2_keep and not pp_drop:
        return rows

    from tools.qc import pay_line_keys

    line_keys = pay_line_keys(rows) if pp_drop else [None] * len(rows)
    kept: list[dict[str, Any]] = []
    for r, line_key in zip(rows, line_keys):
        emp = str(r.get("Employee_ID", ""))
        ws = str(r.get("Worksite_ID", ""))
        pdate = str(r.get("Pay_Date", ""))[:10]
        month = pdate[:7]
        keep_ws = t2_keep.get((emp, month))
        if keep_ws is not None and ws != keep_ws:
            continue  # double-count reassigned away from this unit
        if line_key in pp_drop:
            continue  # scraggly line dropped
        kept.append(r)
    return kept


class ResolveExceptionRequest(BaseModel):
    """Human validation/correction of a QC exception."""
    resolution: str = Field("accept", pattern="^(accept|drop|flag|assign|reopen)$")
    keep_worksite: str | None = None  # test-of-twos: the unit that owns the head
    note: str | None = None
    reviewer: str = "Reviewer"


def _fiscal_window_for(account_id: int | None, tax_year: int, program: str):
    """The client's fiscal window, or None when no rule or statute resolves.

    `account_id` is normalised first: naming the default tenant explicitly and
    leaving it implicit must resolve the same window, or this screen contradicts
    itself depending on how the caller addressed it.
    """
    from infrastructure.payroll.fiscal_source import client_fiscal_window
    from infrastructure.payroll.pay_period_source import configured_account_id
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


@router.get("/ingestion/{tax_year}")
def ingestion_overview(
    tax_year: int,
    state: str = "GA",
    account_id: int | None = None,
) -> dict[str, Any]:
    """Source → canonical → QC for a tax year (default GA).

    Returns the raw-row sample, the field map, the pipeline row counts at each
    transform stage, the pay-code classification split, and the QC exception
    report with any human resolution attached.
    """
    from tools.canonical import RowsAdapter, to_canonical, collapse_to_employee_period
    from tools.qc import run_exception_report

    st = state.upper()
    pref = f"{st}_"
    all_rows = require_pay_periods(account_id=account_id)

    # Raw source sample (state-scoped) — shows Tax_Year vs Pay_Date so the
    # cash-basis trim is visible in the data itself.
    state_rows = [r for r in all_rows if str(r.get("Worksite_ID", "")).startswith(pref)]
    sample = [
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

    # The run selects by the client's FISCAL WINDOW, so that is what this screen
    # counts. `to_canonical`'s calendar-year trim is display-only — nothing
    # statutory reads it — and showing it here claimed a selection the engine
    # never made: 155,293 rows for a client whose run used 384,418.
    program = "GA_JTC" if st == "GA" else f"{st}_JTC"
    window = _fiscal_window_for(account_id, tax_year, program)
    if window is None:
        selected_rows = all_rows
        selection_note = f"no fiscal rule resolved for {tax_year}; all rows carried forward"
    else:
        selected_rows = [
            r for r in all_rows
            if window.begin.isoformat() <= str(r.get("Pay_Date") or "")[:10] <= window.end.isoformat()
        ]
        dropped = len(state_rows) - len([
            r for r in selected_rows if str(r.get("Worksite_ID", "")).startswith(pref)
        ])
        selection_note = (
            f"{window.begin} to {window.end}, read from the client's own fiscal rule; "
            f"{dropped} excluded because the paycheck fell outside the fiscal year"
        )

    recs = [
        r for r in to_canonical(RowsAdapter(selected_rows), program=program)
        if r.worksite_id.startswith(pref)
    ]
    includable = [r for r in recs if r.includable]
    excluded_count = len(recs) - len(includable)
    periods = collapse_to_employee_period(recs)
    pay_code_split = Counter(r.pay_code for r in recs)

    pipeline = [
        {"stage": "Source rows (all years)", "count": len(state_rows),
         "note": f"raw BCS pay-period rows for {st}"},
        {"stage": "Selected by fiscal window (BA-01)", "count": len(recs),
         "note": selection_note},
        {"stage": "Includable after pay-code filter (DATA-05)", "count": len(includable),
         "note": f"{excluded_count} non-wage lines suppressed (mileage / reimbursement)"},
        {"stage": "Collapsed to employee×pay-period", "count": len(periods),
         "note": "one record per employee per pay period"},
    ]

    # QC exception report + attach human resolutions + friendly worksite labels.
    qc = run_exception_report(all_rows, tax_year=tax_year, state=st)
    exceptions: list[dict[str, Any]] = []
    for anomaly in qc["test_of_twos"] + qc["meaningful_pay_period"]:
        eid = _exception_id(anomaly)
        enriched = {**anomaly, "exception_id": eid, "resolution": _QC_RESOLUTIONS.get(eid)}
        if enriched.get("units"):
            enriched["units"] = [
                {**u, "worksite_name": worksite_name(u.get("worksite_id"))}
                for u in enriched["units"]
            ]
        if enriched.get("worksite_id"):
            enriched["worksite_name"] = worksite_name(enriched["worksite_id"])
        exceptions.append(enriched)
    unresolved = sum(1 for e in exceptions if e["resolution"] is None)

    return {
        "as_of": date.today().isoformat(),
        "tax_year": tax_year,
        "state": st,
        "automation": {
            "agents": ["PayrollIngestAgent", "ExceptionReportAgent"],
            "note": "Ingestion is agent-automated; the numbers below are deterministic. "
                    "The human validates exceptions and corrections — the agent never drops a record.",
        },
        "field_map": _FIELD_MAP,
        "raw_sample": sample,
        "pipeline": pipeline,
        "totals": {
            "source_rows": len(state_rows),
            "fiscal_year_rows": len(recs),
            "includable_rows": len(includable),
            "excluded_rows": excluded_count,
            "employee_periods": len(periods),
            "distinct_employees": len({r.employee_id for r in recs}),
            "distinct_worksites": len({r.worksite_id for r in recs}),
        },
        "pay_code_split": [{"pay_code": k, "count": v} for k, v in sorted(pay_code_split.items())],
        "qc": {
            "summary": {**qc["summary"], "unresolved": unresolved},
            "thresholds": qc["thresholds"],
            "exceptions": exceptions,
        },
    }


@router.post("/ingestion/{tax_year}/exceptions/{exception_id}/resolve")
def resolve_exception(
    tax_year: int, exception_id: str, req: ResolveExceptionRequest
) -> dict[str, Any]:
    """Record a human resolution for a QC exception (accept / drop / flag /
    reopen). In-memory; resets on restart — prod persists to the audit store."""
    if req.resolution == "reopen":
        _QC_RESOLUTIONS.pop(exception_id, None)
        return {"ok": True, "exception_id": exception_id, "resolution": None}
    entry = {
        "exception_id": exception_id,
        "resolution": req.resolution,
        "keep_worksite": req.keep_worksite,
        "note": req.note,
        "reviewer": req.reviewer,
        "resolved_at": date.today().isoformat(),
    }
    _QC_RESOLUTIONS[exception_id] = entry
    return {"ok": True, "exception_id": exception_id, "resolution": entry}


#: The source browser's sortable columns. A whitelist: the key arrives from a
#: query string, and an unknown one falls back to the default order rather than
#: sorting on whatever field it happens to name.
_ROW_SORTS: dict[str, tuple[str, bool]] = {
    "employee": ("Employee_ID", False),
    "worksite": ("Worksite_ID", False),
    "fein": ("Entity_FEIN", False),
    "pps": ("Pay_Period_Start", False),
    "ppe": ("Pay_Period_End", False),
    "pay_date": ("Pay_Date", False),
    "tax_year": ("Tax_Year", True),
    "hours": ("Hours_Worked", True),
    "wages": ("Gross_Wages", True),
    "pay_code": ("Pay_Code", False),
}


def _row_sort_key(field: str, numeric: bool):
    def key(r: dict[str, Any]) -> tuple:
        value = r.get(field)
        if numeric:
            try:
                return (0, float(value), str(r.get("Employee_ID", "")))
            except (TypeError, ValueError):
                return (1, 0.0, str(r.get("Employee_ID", "")))
        return (0 if value not in (None, "") else 1, str(value or ""), str(r.get("Pay_Date", "")))
    return key


@router.get("/ingestion/{tax_year}/rows")
def ingestion_rows(
    tax_year: int,
    state: str = "GA",
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    account_id: int | None = None,
    sort: str = "employee",
    order: str = "asc",
) -> dict[str, Any]:
    """Full source browser — paged + searchable, read-only. Rows are the raw BCS
    pay-period lines PAID in `tax_year` for the state (cash-basis), so the
    reviewer can pull up any source row on demand (not just the headline sample).

    Sorted HERE, before paging, so the first page is the top of the whole list
    and not the top of whichever 25 rows happened to be fetched.
    """
    st = state.upper()
    pref = f"{st}_"
    all_rows = require_pay_periods(account_id=account_id)
    scoped = [
        r for r in all_rows
        if str(r.get("Worksite_ID", "")).startswith(pref)
        and str(r.get("Pay_Date", ""))[:4] == str(tax_year)
    ]
    q_l = q.strip().lower()
    if q_l:
        def _match(r: dict[str, Any]) -> bool:
            hay = " ".join(
                str(r.get(k, "")) for k in
                ("Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Date", "Pay_Code")
            ).lower()
            return q_l in hay
        scoped = [r for r in scoped if _match(r)]
    field, numeric = _ROW_SORTS.get(sort, _ROW_SORTS["employee"])
    if sort in _ROW_SORTS:
        scoped.sort(key=_row_sort_key(field, numeric), reverse=order.lower() == "desc")
    else:
        scoped.sort(key=lambda r: (str(r.get("Employee_ID", "")), str(r.get("Pay_Date", ""))))

    total = len(scoped)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    page = scoped[offset:offset + limit]
    rows = [
        {
            "Employee_ID": r.get("Employee_ID"),
            "Worksite_ID": r.get("Worksite_ID"),
            "Worksite_Name": worksite_name(r.get("Worksite_ID")),
            "Entity_FEIN": r.get("Entity_FEIN"),
            "Pay_Period_Start": r.get("Pay_Period_Start"),
            "Pay_Period_End": r.get("Pay_Period_End"),
            "Pay_Date": r.get("Pay_Date"),
            "Tax_Year": r.get("Tax_Year"),
            "Hours_Worked": r.get("Hours_Worked"),
            "Gross_Wages": r.get("Gross_Wages"),
            "Pay_Code": r.get("Pay_Code", "Regular"),
        }
        for r in page
    ]
    return {
        "tax_year": tax_year, "state": st, "q": q,
        "sort": sort if sort in _ROW_SORTS else "employee", "order": order.lower(),
        "total": total, "limit": limit, "offset": offset, "rows": rows,
    }
