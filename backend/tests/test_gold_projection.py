"""The Gold projection. Pure functions, so none of this needs a warehouse.

These are the tests that would have caught the two defects the first live run
hit: a matrix row whose span keys differ between methods, and an eligibility
denominator taken from the wrong collection.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tools import gold_projection as gp
from tools.tokens import record_token

CLIENT = 1001
PROGRAM = "GA_JTC"
YEAR = 2023


def _payroll_row(**overrides):
    base = {
        "Employee_ID": "E1",
        "Worksite_ID": "GA_1",
        "Entity_FEIN": "12-3456789",
        "Job_Title": "Cook",
        "Pay_Period_Start": "2023-01-01",
        "Pay_Period_End": "2023-01-14",
        "Pay_Date": "2023-01-20",
        "Pay_Frequency": "3",
        "Pay_Code": "Regular",
        "Hours_Worked": "68.58",
        "Gross_Wages": "1972.36",
    }
    base.update(overrides)
    return base


# --- money and headcount are Decimal, never float --------------------------


def test_money_arrives_as_decimal_not_float():
    rows = gp.employee_period_fact_rows(
        [_payroll_row()], client_id=CLIENT, program_code=PROGRAM,
        tax_year=YEAR, run_id="R1",
    )
    columns = dict(zip(gp.EMPLOYEE_PERIOD_FACT_COLUMNS, rows[0]))

    assert isinstance(columns["wages"], Decimal)
    assert isinstance(columns["hours"], Decimal)
    # Exact, because it went through the source string rather than a float.
    assert columns["wages"] == Decimal("1972.36")
    assert columns["hours"] == Decimal("68.58")


def test_a_float_source_still_lands_exactly():
    """0.1 + 0.2 is the classic. The projection must not carry that in."""
    rows = gp.employee_period_fact_rows(
        [_payroll_row(Gross_Wages=0.1 + 0.2)], client_id=CLIENT,
        program_code=PROGRAM, tax_year=YEAR, run_id="R1",
    )
    wages = dict(zip(gp.EMPLOYEE_PERIOD_FACT_COLUMNS, rows[0]))["wages"]
    assert wages == Decimal("0.30")


def test_period_days_is_inclusive_of_both_ends():
    rows = gp.employee_period_fact_rows(
        [_payroll_row()], client_id=CLIENT, program_code=PROGRAM,
        tax_year=YEAR, run_id="R1",
    )
    assert dict(zip(gp.EMPLOYEE_PERIOD_FACT_COLUMNS, rows[0]))["period_days"] == 14


# --- the drill key is imported, never re-derived ---------------------------


def test_every_table_mints_the_same_record_token():
    expected = record_token(CLIENT, PROGRAM, YEAR, "E1")

    fact = dict(zip(gp.EMPLOYEE_PERIOD_FACT_COLUMNS, gp.employee_period_fact_rows(
        [_payroll_row()], client_id=CLIENT, program_code=PROGRAM,
        tax_year=YEAR, run_id="R1")[0]))
    eligibility = dict(zip(gp.EMPLOYEE_ELIGIBILITY_COLUMNS, gp.employee_eligibility_rows(
        totals=[{"Employee_ID": "E1", "total_hours": 1, "total_wages": 2}],
        averages=[], client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        method="min_max", run_id="R1")[0]))
    matrix = dict(zip(gp.ONEZERO_MATRIX_COLUMNS, gp.onezero_matrix_rows(
        [{"Employee_ID": "E1", "Worksite_ID": "GA_1", "first_pps": "2023-01-01",
          "last_ppe": "2023-12-31", "weight": 1.0, "months": [1.0] * 12}],
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        method="min_max", run_id="R1")[0]))

    assert fact["record_token"] == expected
    assert eligibility["record_token"] == expected
    assert matrix["record_token"] == expected


# --- the denominator is everyone with payroll ------------------------------


def test_an_employee_with_totals_but_no_qualifying_period_still_gets_a_row():
    """156 of the reference client's 10,236 are in this position.

    Taking the denominator from `all_averages` reports 10,080 and looks entirely
    plausible, which is why this is asserted rather than assumed.
    """
    totals = [
        {"Employee_ID": "E1", "total_hours": 100, "total_wages": 5000},
        {"Employee_ID": "E2", "total_hours": 3, "total_wages": 40},
    ]
    averages = [{
        "Employee_ID": "E1", "total_hours": 100, "total_wages": 5000,
        "first_start": "2023-01-01", "last_end": "2023-06-30", "days": 180,
        "weeks_worked": 26.0, "avg_weekly_hours": 38.5, "avg_weekly_wages": 700.0,
        "weight": 1.0, "eligible": True,
    }]

    rows = gp.employee_eligibility_rows(
        totals=totals, averages=averages, client_id=CLIENT, program_code=PROGRAM,
        tax_year=YEAR, method="min_max", run_id="R1",
    )
    by_employee = {
        dict(zip(gp.EMPLOYEE_ELIGIBILITY_COLUMNS, row))["employee_id"]:
        dict(zip(gp.EMPLOYEE_ELIGIBILITY_COLUMNS, row))
        for row in rows
    }

    assert set(by_employee) == {"E1", "E2"}
    assert by_employee["E1"]["eligible"] == 1
    # Evaluated and did not qualify - NOT "never looked at".
    assert by_employee["E2"]["eligible"] == 0
    assert by_employee["E2"]["avg_weekly_hours"] is None
    assert by_employee["E2"]["total_wages"] == Decimal("40.00")


def test_eligible_is_a_bit_not_a_bool():
    rows = gp.employee_eligibility_rows(
        totals=[{"Employee_ID": "E1", "total_hours": 1, "total_wages": 1}],
        averages=[{"Employee_ID": "E1", "eligible": True, "weight": 1.0}],
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        method="min_max", run_id="R1",
    )
    assert dict(zip(gp.EMPLOYEE_ELIGIBILITY_COLUMNS, rows[0]))["eligible"] == 1


# --- the two methods publish the span under different keys -----------------


def test_pay_period_matrix_rows_carry_their_span():
    """Pay Period emits Pay_Period_Start/End; Min-Max emits first_pps/last_ppe.

    Reading only one shape wrote NULL into a NOT NULL column for every row of
    the other method, which is exactly how the first live run failed.
    """
    rows = gp.onezero_matrix_rows(
        [{"Employee_ID": "E1", "Worksite_ID": "GA_1",
          "Pay_Period_Start": "2023-03-01", "Pay_Period_End": "2023-03-14",
          "weight": 1.0, "months": [0] * 12}],
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        method="pay_period", run_id="R1",
    )
    columns = dict(zip(gp.ONEZERO_MATRIX_COLUMNS, rows[0]))

    assert columns["first_pps"] == date(2023, 3, 1)
    assert columns["last_ppe"] == date(2023, 3, 14)


def test_a_matrix_row_with_no_span_at_all_raises():
    with pytest.raises(ValueError, match="no period span"):
        gp.onezero_matrix_rows(
            [{"Employee_ID": "E1", "Worksite_ID": "GA_1", "weight": 1.0,
              "months": [0] * 12}],
            client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
            method="min_max", run_id="R1",
        )


def test_short_month_lists_are_padded_to_twelve():
    rows = gp.onezero_matrix_rows(
        [{"Employee_ID": "E1", "Worksite_ID": "GA_1", "first_pps": "2023-01-01",
          "last_ppe": "2023-02-01", "weight": 1.0, "months": [1.0, 1.0]}],
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        method="min_max", run_id="R1",
    )
    columns = dict(zip(gp.ONEZERO_MATRIX_COLUMNS, rows[0]))
    assert columns["month_12"] == Decimal("0.00")


# --- the divisor is twelve, always -----------------------------------------


def test_average_headcount_divides_by_twelve_including_empty_months():
    """Validation 9.8 asserts this in SQL. This asserts it before the write."""
    summary = [{
        "Worksite_ID": "GA_1",
        "month_totals": [10, 10, 10, 10, 10, 10, 0, 0, 0, 0, 0, 0],
        "total": 60.0,
        "average_headcount": 5.0,
    }]
    rows = gp.unit_month_summary_rows(
        summary, client_id=CLIENT, tax_year=YEAR, method="min_max",
        run_id="R1", unreachable=[10, 11],
    )
    columns = dict(zip(gp.UNIT_MONTH_SUMMARY_COLUMNS, rows[0]))

    assert columns["total"] == Decimal("60.00")
    assert columns["average_headcount"] == Decimal("5.00")
    assert columns["average_headcount"] == (columns["total"] / 12).quantize(Decimal("0.01"))
    assert columns["months_with_headcount"] == 6
    assert columns["unreachable_months"] == "10,11"


# --- run identity -----------------------------------------------------------


def test_calculation_id_is_stable_for_the_same_inputs():
    args = dict(
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        window_begin=date(2023, 1, 1), window_end=date(2023, 12, 31),
        floors={"minimum_average_weekly_hours": 35.0,
                "minimum_average_weekly_wages_usd": 636.0,
                "source": "rules/ga_jtc/2023.json"},
        assumption_ids=["GDS-STEP1-2026-08-25-v8"],
        rows=[_payroll_row()],
    )
    assert gp.calculation_id(**args) == gp.calculation_id(**args)


def test_calculation_id_moves_when_the_payroll_moves():
    common = dict(
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        window_begin=date(2023, 1, 1), window_end=date(2023, 12, 31),
        floors={"source": "rules/ga_jtc/2023.json"},
        assumption_ids=["GDS-STEP1-2026-08-25-v8"],
    )
    before = gp.calculation_id(**common, rows=[_payroll_row()])
    after = gp.calculation_id(**common, rows=[_payroll_row(Gross_Wages="1972.37")])
    assert before != after


def test_calculation_id_moves_when_the_statute_moves():
    common = dict(
        client_id=CLIENT, program_code=PROGRAM, tax_year=YEAR,
        window_begin=date(2023, 1, 1), window_end=date(2023, 12, 31),
        assumption_ids=["GDS-STEP1-2026-08-25-v8"],
        rows=[_payroll_row()],
    )
    before = gp.calculation_id(**common, floors={"minimum_average_weekly_wages_usd": 636.0})
    after = gp.calculation_id(**common, floors={"minimum_average_weekly_wages_usd": 700.0})
    assert before != after
