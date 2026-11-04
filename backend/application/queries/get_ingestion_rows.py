"""The full source browser: raw pay-period lines, paged, searchable and sortable. Read-only.

Rows are the raw BCS pay-period lines PAID in `tax_year` for the state (cash-basis), so
a reviewer can pull up any source row on demand and not just the headline sample.

Sorted BEFORE paging, so the first page is the top of the whole list and not the top of
whichever rows happened to be fetched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.payroll_rows import require_pay_periods

#: The source browser's sortable columns. A whitelist: the key arrives from a
#: query string, and an unknown one falls back to the default order rather than
#: sorting on whatever field it happens to name.
ROW_SORTS: dict[str, tuple[str, bool]] = {
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


@dataclass(frozen=True)
class GetIngestionRowsQuery(Query):
    """One page of the source browser, filtered by `q` and sorted by `sort` before paging."""

    tax_year: int
    state: str = "GA"
    q: str = ""
    limit: int = 50
    offset: int = 0
    account_id: int | None = None
    sort: str = "employee"
    order: str = "asc"


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


def _matches(row: dict[str, Any], needle: str) -> bool:
    hay = " ".join(
        str(row.get(k, "")) for k in ("Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Date", "Pay_Code")
    ).lower()
    return needle in hay


def _sorted(rows: list[dict[str, Any]], sort: str, order: str) -> None:
    if sort in ROW_SORTS:
        field, numeric = ROW_SORTS[sort]
        rows.sort(key=_row_sort_key(field, numeric), reverse=order.lower() == "desc")
    else:
        rows.sort(key=lambda r: (str(r.get("Employee_ID", "")), str(r.get("Pay_Date", ""))))


def _shown(row: dict[str, Any]) -> dict[str, Any]:
    from data.sites import worksite_name

    return {
        "Employee_ID": row.get("Employee_ID"),
        "Worksite_ID": row.get("Worksite_ID"),
        "Worksite_Name": worksite_name(row.get("Worksite_ID")),
        "Entity_FEIN": row.get("Entity_FEIN"),
        "Pay_Period_Start": row.get("Pay_Period_Start"),
        "Pay_Period_End": row.get("Pay_Period_End"),
        "Pay_Date": row.get("Pay_Date"),
        "Tax_Year": row.get("Tax_Year"),
        "Hours_Worked": row.get("Hours_Worked"),
        "Gross_Wages": row.get("Gross_Wages"),
        "Pay_Code": row.get("Pay_Code", "Regular"),
    }


def handle_get_ingestion_rows(query: GetIngestionRowsQuery) -> dict[str, Any]:
    """The matching pay-period lines for the page, with the total before paging."""
    st = query.state.upper()
    prefix = f"{st}_"
    all_rows = require_pay_periods(account_id=query.account_id)
    scoped = [
        r for r in all_rows
        if str(r.get("Worksite_ID", "")).startswith(prefix)
        and str(r.get("Pay_Date", ""))[:4] == str(query.tax_year)
    ]
    needle = query.q.strip().lower()
    if needle:
        scoped = [r for r in scoped if _matches(r, needle)]
    _sorted(scoped, query.sort, query.order)

    limit = max(1, min(int(query.limit), 200))
    offset = max(0, int(query.offset))
    return {
        "tax_year": query.tax_year, "state": st, "q": query.q,
        "sort": query.sort if query.sort in ROW_SORTS else "employee", "order": query.order.lower(),
        "total": len(scoped), "limit": limit, "offset": offset,
        "rows": [_shown(r) for r in scoped[offset:offset + limit]],
    }
