"""Public parity gate: the committed synthetic dataset through the
PRODUCTION engine. [WL-11, D21]

Unlike `test_engine_parity_reference.py`, this never skips: the fixture
(`backend/data/payroll_pay_periods.csv`) is a committed, synthetic file, so a
clone of the public repository can run it with no private extract and no
`TCC_REQUIRE_PARITY` flag. CI runs this gate; it does not run the private one
(no fixtures, no flag) — see `certified_synthetic.py` for why this is a
regression pin rather than a cross-implementation agreement.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from certified_synthetic import (
    CERTIFIED_SYNTHETIC_EMPLOYEES,
    CERTIFIED_SYNTHETIC_MIN_MAX_ELIGIBLE,
    CERTIFIED_SYNTHETIC_PAY_PERIOD_ELIGIBLE,
    CERTIFIED_SYNTHETIC_TAX_YEAR,
    FISCAL_WINDOW,
    ANALYSIS_START_MONTH,
    assert_synthetic_year_pack_agrees,
    certified_synthetic_pack,
)
from domain.calculation.onezero import run_min_max_method, run_pay_period_method

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SYNTHETIC_CSV = _BACKEND_ROOT / "data" / "payroll_pay_periods.csv"


def _synthetic_ga_rows(tax_year: int) -> list[dict]:
    """Georgia rows for one tax year, already in the engine's BCS shape.

    `payroll_pay_periods.csv` is written in the same column shape the private
    gate's `_bcs_rows()` produces, so it needs no mapping — just a numeric
    cast and a filter to the jurisdiction and year this gate prices.
    """
    rows = []
    with _SYNTHETIC_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["Tax_Year"]) != tax_year or not row["Worksite_ID"].startswith("GA_"):
                continue
            rows.append({
                **row,
                "Tax_Year": int(row["Tax_Year"]),
                "Hours_Worked": float(row["Hours_Worked"]),
                "Gross_Wages": float(row["Gross_Wages"]),
            })
    return rows


@pytest.fixture(scope="module")
def production():
    rows = _synthetic_ga_rows(CERTIFIED_SYNTHETIC_TAX_YEAR)
    common = {
        "tax_year": CERTIFIED_SYNTHETIC_TAX_YEAR,
        "analysis_start_month": ANALYSIS_START_MONTH,
        "pack": certified_synthetic_pack(),
        "fiscal_window": FISCAL_WINDOW,
    }
    return {
        "min_max": run_min_max_method(rows, **common),
        "pay_period": run_pay_period_method(rows, **common),
    }


def test_the_synthetic_fixture_is_committed_and_present():
    """A clone of the public repo must be able to run this gate with nothing
    extra staged — that is the entire point of using a synthetic dataset."""
    assert _SYNTHETIC_CSV.exists(), (
        f"{_SYNTHETIC_CSV} is missing. Unlike the private reference extract, "
        "this file is tracked and must be committed."
    )


def test_certified_synthetic_floors_match_the_year_pack():
    """The TY2024 GA JTC pack still carries the floors this gate used."""
    assert_synthetic_year_pack_agrees()


def test_synthetic_population_matches(production):
    assert len(production["min_max"].total_hours_and_wages) == CERTIFIED_SYNTHETIC_EMPLOYEES
    assert len(production["pay_period"].total_hours_and_wages) == CERTIFIED_SYNTHETIC_EMPLOYEES


def test_synthetic_min_max_eligibility_matches(production):
    actual = {row["Employee_ID"] for row in production["min_max"].eligible_employees}
    assert len(actual) == CERTIFIED_SYNTHETIC_MIN_MAX_ELIGIBLE


def test_synthetic_pay_period_eligibility_matches(production):
    actual = {row["Employee_ID"] for row in production["pay_period"].eligible_employees}
    assert len(actual) == CERTIFIED_SYNTHETIC_PAY_PERIOD_ELIGIBLE
