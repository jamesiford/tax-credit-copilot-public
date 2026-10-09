"""Average Headcount is measured over the CLIENT's twelve months, not January's.

`average_headcount` is the number a base year is set from, and the base year is
the most leveraged input in the model — everything downstream is measured
against it. It took the calendar year, which is right only for a calendar filer.

Candle Bottle's payroll runs 3 Aug 2023 to 9 Aug 2024. Measured over calendar
2023 it kept five months of that, scored the seven measuring dates before the
first pay date as zero, still divided by twelve, and reported **226.76** against
a certified Pay Period average of **494.25**. TY2023 is its base year, so no
wrong dollar reached a screen — but the moment a second year of payroll lands,
net-new is measured against a base understated by ~268 jobs.

These are offline: synthetic rows, an explicit window, no lakehouse.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from domain.calculation.headcount import average_headcount, rows_for_state_year
from tools.credit_math import load_pack_one_zero

#: The authored GA pack — a file, so this stays offline. These tests are about
#: the WINDOW, and the synthetic rows clear both floors comfortably.
_PACK = load_pack_one_zero("GA", tax_year=2023)


def _weeks(start: date, count: int):
    """Consecutive weekly pay periods from `start`."""
    for index in range(count):
        begin = start + timedelta(days=7 * index)
        yield begin, begin + timedelta(days=6)


def _payroll(employees: int, start: date, weeks: int) -> list[dict]:
    """`employees` people, each worked full time for `weeks` weeks from `start`."""
    rows = []
    for person in range(employees):
        for begin, end in _weeks(start, weeks):
            rows.append({
                "Employee_ID": f"E{person:04d}",
                "Worksite_ID": "GA_ONE",
                "Work_State": "GA",
                "Pay_Period_Start": begin.isoformat(),
                "Pay_Period_End": end.isoformat(),
                "Pay_Date": (end + timedelta(days=4)).isoformat(),
                "Hours_Worked": 40.0,
                "Gross_Wages": 1000.0,
            })
    return rows


#: A year of payroll that opens in August, like the reference client.
AUGUST_FILER = _payroll(employees=10, start=date(2023, 8, 1), weeks=53)


class TestRowSelection:
    def test_without_a_window_it_keeps_the_calendar_year(self):
        """The fallback, unchanged. Right for a calendar filer and nobody else."""
        rows = rows_for_state_year(AUGUST_FILER, "GA", 2023)
        dates = sorted(r["Pay_Date"] for r in rows)
        assert dates[0].startswith("2023-08")
        assert dates[-1].startswith("2023-12")

    def test_a_window_keeps_the_client_s_own_twelve_months(self):
        rows = rows_for_state_year(
            AUGUST_FILER, "GA", 2023, (date(2023, 7, 28), date(2024, 8, 2)),
        )
        dates = sorted(r["Pay_Date"] for r in rows)
        assert dates[0].startswith("2023-08")
        assert dates[-1].startswith("2024-0")
        assert len(rows) > len(rows_for_state_year(AUGUST_FILER, "GA", 2023))

    def test_a_row_with_no_parseable_pay_date_falls_outside_every_window(self):
        # Silently including it would place payroll in a year nobody can name.
        rows = rows_for_state_year(
            [{"Work_State": "GA", "Pay_Date": ""}], "GA", 2023,
            (date(2023, 1, 1), date(2023, 12, 31)),
        )
        assert rows == []


class TestTheWindowMovesTheAnswer:
    def test_a_non_calendar_filer_is_understated_by_the_calendar_year(self):
        """The defect, in miniature.

        Seven of the twelve calendar-2023 measuring dates fall before this
        client's first pay period, and the divisor is still twelve.
        """
        calendar = average_headcount(AUGUST_FILER, "GA", 2023, _PACK)
        fiscal = average_headcount(
            AUGUST_FILER, "GA", 2023, _PACK, (date(2023, 7, 28), date(2024, 8, 2)),
        )
        assert calendar < fiscal
        assert fiscal == pytest.approx(10.0, abs=0.5), "ten people employed all year"
        assert calendar == pytest.approx(10.0 * 5 / 12, abs=1.0)

    def test_a_calendar_filer_is_unaffected(self):
        """The fallback and the real window agree where the client is a calendar filer.

        This is why the mistake survived: four of the five clients on the book
        are calendar filers and the two paths agreed for every one of them.
        """
        calendar_filer = _payroll(employees=10, start=date(2023, 1, 2), weeks=52)
        assert average_headcount(calendar_filer, "GA", 2023, _PACK) == pytest.approx(
            average_headcount(
                calendar_filer, "GA", 2023, _PACK, (date(2023, 1, 1), date(2023, 12, 31)),
            )
        )


class TestTheMeasuringDatesStartWhereThePayrollDoes:
    def test_a_year_opening_mid_month_does_not_burn_month_one(self):
        """`first_measurable_month`, not `window.begin`.

        Candle Bottle's window opens 2023-07-28 and nothing spans 2023-07-31, so
        starting the twelve months there scores Month 1 zero AND pushes the real
        final month off the end. Taking `begin` directly reported 451.71 against
        a certified 494.25.
        """
        stub = average_headcount(
            AUGUST_FILER, "GA", 2023, _PACK, (date(2023, 7, 28), date(2024, 8, 2)),
        )
        clean = average_headcount(
            AUGUST_FILER, "GA", 2023, _PACK, (date(2023, 8, 1), date(2024, 7, 31)),
        )
        # The stub month must not cost anything: both windows measure the same
        # twelve months because the walk skips the date no pay period reaches.
        assert stub == pytest.approx(clean, abs=0.01)
