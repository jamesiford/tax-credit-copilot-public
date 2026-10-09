"""Tests for the canonical source-record interface (Part E · DATA-03/04/05/06)."""
from __future__ import annotations

from datetime import date

from tools import canonical as C


class _StubAdapter:
    def __init__(self, rows):
        self._rows = rows

    def rows(self):
        return self._rows


def _raw(emp="E1", unit="GA_ATL_HQ", pay_date="2025-02-02", code="Regular", wages=2000, hours=80,
         start="2025-01-15", end="2025-01-28", fein="58-1234567"):
    return {
        "Tax_Year": "2025",
        "Employee_ID": emp,
        "Job_Title": "Analyst",
        "Worksite_ID": unit,
        "Pay_Period_Start": start,
        "Pay_Period_End": end,
        "Pay_Date": pay_date,
        "Entity_FEIN": fein,
        "Hours_Worked": str(hours),
        "Gross_Wages": str(wages),
        "Pay_Code": code,
    }


def test_maps_to_canonical_record_shape():
    recs = C.to_canonical(_StubAdapter([_raw()]), tax_year=2025)
    assert len(recs) == 1
    r = recs[0]
    assert isinstance(r, C.CanonicalRecord)
    assert r.employee_id == "E1"
    assert r.worksite_id == "GA_ATL_HQ"
    assert r.legal_entity_fein == "58-1234567"
    assert r.pay_date == date(2025, 2, 2)
    assert r.unit_number == "GA_ATL_HQ"  # DATA-04 join populates unit


def test_frequency_inferred_from_period_span():
    weekly = C.to_canonical(_StubAdapter([_raw(start="2025-01-01", end="2025-01-07")]))[0]
    biweekly = C.to_canonical(_StubAdapter([_raw(start="2025-01-01", end="2025-01-14")]))[0]
    assert weekly.pay_frequency == "weekly"
    assert biweekly.pay_frequency == "biweekly"


def test_cash_basis_fiscal_year_trim_by_pay_date():
    rows = [
        _raw(pay_date="2025-01-05"),   # in year
        _raw(pay_date="2024-12-28"),   # earned prior, paid prior -> excluded from 2025
        _raw(pay_date="2026-01-03"),   # paid next year -> excluded
    ]
    recs = C.to_canonical(_StubAdapter(rows), tax_year=2025)
    assert len(recs) == 1
    assert recs[0].pay_date.year == 2025


def test_pay_code_classification_excludes_non_taxable():
    rows = [_raw(code="Regular"), _raw(code="Mileage", wages=25, hours=0)]
    recs = C.to_canonical(_StubAdapter(rows), tax_year=2025, program="GA_JTC")
    by_code = {r.pay_code: r.includable for r in recs}
    assert by_code["Regular"] is True
    assert by_code["Mileage"] is False  # DATA-05 strips non-taxable


def test_collapse_drops_non_includable_from_wage_base():
    rows = [
        _raw(code="Regular", wages=2000, hours=80),
        _raw(code="Mileage", wages=50, hours=0),
    ]
    recs = C.to_canonical(_StubAdapter(rows), tax_year=2025, program="GA_JTC")
    collapsed = C.collapse_to_employee_period(recs)
    assert len(collapsed) == 1
    # mileage excluded from the wage base
    assert collapsed[0]["gross_wages"] == 2000.0
    assert collapsed[0]["hours_worked"] == 80.0


def test_default_adapter_reads_real_csv():
    # Runs on the prototype pay-period CSV; must map a non-trivial number of rows.
    recs = C.to_canonical(tax_year=2025)
    assert len(recs) > 100
    assert all(r.tax_year == 2025 for r in recs)
    assert all(r.pay_date.year == 2025 for r in recs)
