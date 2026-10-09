"""Average Headcount, and the row selection it depends on.

**One definition, called by everything.** These functions exist because they
were once three: the assessment filtered on the pay date's year, the what-if
simulator filtered on the `Tax_Year` column, and they disagreed at the fiscal
boundary. Position quoted $0 for a client-year while Plan quoted $252,280 for
the same one — indefensible whichever was right.

They live in the domain rather than beside a router because Average Headcount is
the quantity the credit is computed from. It is a statutory concept, not a
detail of how one screen fetches data, and a second implementation of it is a
second answer.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def row_state(row: dict[str, Any]) -> str:
    """The work state for one pay-period row.

    Two shapes are in play. The lakehouse projection carries an explicit
    `Work_State`; the older CSV fixture encodes it only as the `Worksite_ID`
    prefix (`GA_SAV_DC`). This prefers the explicit column and falls back to the
    prefix.

    One function rather than two readings, because the failure mode is silent: a
    caller reading only `Work_State` gets an empty set on CSV data and concludes
    the client operates nowhere, which renders as an empty screen rather than an
    error.
    """
    explicit = (row.get("Work_State") or "").strip()
    if explicit:
        return explicit.upper()
    worksite = str(row.get("Worksite_ID") or "")
    head, sep, _ = worksite.partition("_")
    return head.upper() if sep and len(head) == 2 else ""


def states_present(rows: list[dict[str, Any]]) -> list[str]:
    """Every work state appearing in these rows, sorted."""
    return sorted({s for s in (row_state(r) for r in rows) if s})


def rows_for_state_year(
    rows: list[dict[str, Any]],
    state: str,
    tax_year: int,
    window: tuple[date, date] | None = None,
) -> list[dict[str, Any]]:
    """The rows one state-year's Average Headcount is computed from.

    Selection is by **pay date**, matching the fiscal trim the certified run
    uses. Filtering on a `Tax_Year` column instead moves rows across the
    boundary and changes the answer.

    `window` is the client's own fiscal year. Without one this falls back to the
    calendar year, which is right only for a calendar filer — see
    `average_headcount`.
    """
    if window is None:
        return [
            r for r in rows
            if row_state(r) == state and str(r.get("Pay_Date") or "")[:4] == str(tax_year)
        ]
    begin, end = window
    return [
        r for r in rows
        if row_state(r) == state and begin <= _pay_date(r) <= end
    ]


def _pay_date(row: dict[str, Any]) -> date:
    """`Pay_Date` as a date. Unparseable rows sort outside every window."""
    raw = str(row.get("Pay_Date") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return date.min


def average_headcount(
    rows: list[dict[str, Any]],
    state: str,
    tax_year: int,
    pack: Any,
    window: tuple[date, date] | None = None,
) -> float:
    """Average Headcount for one state-year.

    The analysis window is passed **explicitly** rather than inferred, so every
    caller measures over the same span. An inferred window was the other half of
    the Position-versus-Plan disagreement: the two paths selected different rows
    *and* measured them over different spans.

    **Pass the client's own fiscal window.** Falling back to the calendar year
    is correct only for a calendar filer, and silently wrong for anybody else:
    Candle Bottle's payroll runs 3 Aug 2023 to 9 Aug 2024, so a Jan-Dec 2023
    window kept five months of it, scored the seven months before the first pay
    date as zero, and still divided by twelve — 226.76 against the certified
    410.13. The base year is the most leveraged input in the model, and this is
    the number it is set from.

    The twelve measuring dates start at `first_measurable_month`, NOT at the
    window's own month — the same derivation `ClientRun.engine_kwargs` uses. A
    year opening mid-month opens on a stub no pay period spans, and starting
    there burns Month 1 and pushes the real final month off the end. Taking
    `begin` directly here reported Candle Bottle at 451.71.
    """
    from domain.calculation.onezero import first_measurable_month, run_pay_period_method

    begin, end = window or (date(tax_year, 1, 1), date(tax_year, 12, 31))
    year_rows = rows_for_state_year(rows, state, tax_year, window)
    if not year_rows:
        return 0.0
    return run_pay_period_method(
        year_rows,
        tax_year=tax_year,
        analysis_start_month=first_measurable_month(year_rows, (begin, end)),
        pack=pack,
        fiscal_window=(begin, end),
    ).annual_average
