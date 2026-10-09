"""The SQL scope read must agree with the row projection it replaced.

`/api/scope/client/{id}` used to materialise every payroll row to answer three
DISTINCTs. It now asks the warehouse. That is only safe if both paths select the
same row population and resolve state the same way, so this crosses the boundary
rather than testing either side alone.

The live half is opt-in (`TCC_FABRIC_TESTS=1`) because CI has no lakehouse. The
offline half runs everywhere and pins the fallback's shape.
"""
from __future__ import annotations

import os

import pytest

from infrastructure.persistence.source_sql import (
    SourceSqlReader,
    PayrollScope,
    payroll_scope_from_rows,
)

LIVE = os.getenv("TCC_FABRIC_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="needs a Fabric lakehouse; set TCC_FABRIC_TESTS=1")

REFERENCE_ACCOUNT = 1001


def test_the_fallback_derives_every_field_from_rows():
    rows = [
        {"Tax_Year": 2023, "Work_State": "ga", "Pay_Date": "2023-08-15", "Worksite_ID": "GA_1"},
        {"Tax_Year": 2023, "Work_State": "GA", "Pay_Date": "2023-08-31", "Worksite_ID": "GA_1"},
        {"Tax_Year": 2024, "Work_State": "GA", "Pay_Date": "2024-01-15", "Worksite_ID": "GA_2"},
    ]
    scope = payroll_scope_from_rows(rows)

    assert scope.total_rows == 3
    assert scope.tax_years == [2023, 2024]
    assert scope.states == ["GA"], "row_state upper-cases, so 'ga' and 'GA' are one state"
    assert scope.pay_dates == ["2023-08-15", "2023-08-31", "2024-01-15"]


def test_a_row_with_no_pay_date_contributes_no_month():
    """Q1: `Pay_Date` is nullable. It still has a tax year, from the period end."""
    scope = payroll_scope_from_rows(
        [{"Tax_Year": 2023, "Work_State": "GA", "Pay_Date": None, "Worksite_ID": "GA_1"}]
    )

    assert scope.total_rows == 1
    assert scope.tax_years == [2023]
    assert scope.pay_dates == [], "a null pay date cannot be bucketed into a month"


def test_dates_are_deduplicated_not_counted():
    """`pay_dates` is DISTINCT dates. Two years of payroll is a few hundred, not 384,433."""
    rows = [
        {"Tax_Year": 2023, "Work_State": "GA", "Pay_Date": "2023-08-15", "Worksite_ID": "GA_1"}
        for _ in range(500)
    ]
    scope = payroll_scope_from_rows(rows)

    assert scope.total_rows == 500, "the row count is still the true row count"
    assert scope.pay_dates == ["2023-08-15"]


def test_an_unconfigured_reader_declines_rather_than_raising(monkeypatch):
    """False sends the caller to the row path; an exception would 500 the endpoint."""
    monkeypatch.delenv("FABRIC_LAKEHOUSE", raising=False)

    assert SourceSqlReader().is_configured() is False


@live_only
def test_the_sql_and_the_row_projection_agree(monkeypatch):
    """The join that matters. A disagreement here changes which years a client can file.

    `conftest` pins `DATA_SOURCE=csv` for the whole suite so CI can run offline.
    That pin has to be lifted here or the row half reads the 9,477-row fixture
    and the comparison is against the wrong dataset entirely.
    """
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    from infrastructure.payroll.pay_period_source import load_pay_periods

    reader = SourceSqlReader()
    assert reader.is_configured(), "TCC_FABRIC_TESTS=1 but no lakehouse is configured"

    from_sql = reader.payroll_scope(REFERENCE_ACCOUNT)
    from_rows = payroll_scope_from_rows(load_pay_periods(REFERENCE_ACCOUNT))

    assert from_sql.total_rows == from_rows.total_rows
    assert from_sql.tax_years == from_rows.tax_years
    assert from_sql.states == from_rows.states
    assert from_sql.pay_dates == from_rows.pay_dates


@live_only
def test_the_reference_client_still_reports_two_years_in_georgia():
    scope = SourceSqlReader().payroll_scope(REFERENCE_ACCOUNT)

    assert isinstance(scope, PayrollScope)
    assert scope.total_rows == 384_433
    assert scope.tax_years == [2023, 2024]
    assert scope.states == ["GA"]
