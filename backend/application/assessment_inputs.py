"""What an assessment reads from payroll: its years, its window and its thin-year guards.

Split from `assessment.py` so the orchestration there stays short. Average Headcount is
a statutory quantity, so its definition lives in `domain.calculation.headcount`; the
names are re-exported here because the simulator and the assessment already import them
from one place, and a second implementation would be a second answer.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from application.source_ports import window_for_state_year
from domain.calculation.headcount import average_headcount as _average_headcount
from domain.calculation.headcount import rows_for_state_year as _rows_for_state_year

#: Months of payroll a fiscal year needs before it is worth averaging over
#: twelve. Matches `_MIN_REACHABLE_MONTHS` in the unit trend, which declines a
#: year for the same reason.
MIN_MONTHS_TO_ASSESS = 6

#: Fewer rows than this in a state-year is too thin to mean anything.
MIN_ROWS_TO_ASSESS = 50


def fiscal_years(rows: list[dict[str, Any]]) -> list[int]:
    """Tax years present in the payroll, by pay date.

    Deliberately NOT via `fiscal_year_of`: that labels a fiscal year by the year
    it ends, while Georgia's regulation labels a tax year by the year it begins,
    and the two disagree for every non-calendar filer. See the strict xfail in
    `tests/test_ga_wage_table.py`. Until the partner rules, this uses the pay date's own
    year, which is the reading the certified reference run already uses.
    """
    years = set()
    for row in rows:
        pay_date = str(row.get("Pay_Date") or "")[:10]
        if pay_date:
            years.add(date.fromisoformat(pay_date).year)
    return sorted(years)


def rows_for_state_year(
    rows: list[dict[str, Any]],
    state: str,
    tax_year: int,
    window: tuple[date, date] | None = None,
) -> list[dict[str, Any]]:
    """Re-exported from `domain.calculation.headcount`; see the module docstring."""
    return _rows_for_state_year(rows, state, tax_year, window)


def average_headcount(
    rows: list[dict[str, Any]],
    state: str,
    tax_year: int,
    pack: Any,
    window: tuple[date, date] | None = None,
) -> float:
    """Re-exported from `domain.calculation.headcount`; see the module docstring."""
    return _average_headcount(rows, state, tax_year, pack, window)


def months_with_payroll(rows: list[dict[str, Any]]) -> int:
    """Distinct calendar months the selected rows actually pay into."""
    return len({str(r.get("Pay_Date") or "")[:7] for r in rows if r.get("Pay_Date")})


def client_window(client_id: int, state: str, tax_year: int) -> tuple[date, date] | None:
    """The client's own fiscal year, or None to fall back to the calendar year.

    Resolved by the same adapter the certified run uses. Without it a
    non-calendar filer is measured over the wrong twelve months: Candle Bottle
    came out at 226.76 against a certified 494.25, because five months of its
    payroll landed inside calendar 2023 and the other seven measuring dates
    scored zero.
    """
    return window_for_state_year(client_id, state, tax_year)
