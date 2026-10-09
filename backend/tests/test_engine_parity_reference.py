"""Parity gate: the partner's reference dataset through the PRODUCTION engine.

The certified v7 rules were derived and proven in `tools/reference_*.py`, which is
a benchmark harness — it is not what the product runs. Everything a user sees
comes out of `tools/onezero.py`. This module asserts the two agree.

That is the whole point of the convergence work described in
`docs/architecture/ENGINE-CONVERGENCE.md`: without this test, the app can drift
from the numbers we certified with the partner and nothing would notice.

The test is skipped when the reference source files are absent, so a clone without
the partner's confidential payroll extract still runs green.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
from pathlib import Path

import pytest

from certified import (
    CERTIFIED_EMPLOYEES,
    CERTIFIED_MIN_MAX_ELIGIBLE,
    CERTIFIED_PAY_PERIOD_ELIGIBLE,
    FISCAL_WINDOW,
    MIN_WEEKLY_HOURS,
    MIN_WEEKLY_WAGES,
    certified_pack,
    assert_year_pack_agrees,
)
from tools.reference_source import TccPayrollAdapter
from tools.reference_step1 import run_reference_step1
from domain.calculation.onezero import (
    OneZeroMethodology,
    OneZeroPack,
    run_min_max_method,
    run_pay_period_method,
)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_DIR = _BACKEND_ROOT / "data" / "payroll"
_SOURCE_FILES = ("One.csv", "Two.csv", "Three.csv", "Four.csv")
_FIXTURES_PRESENT = all((_SOURCE_DIR / name).exists() for name in _SOURCE_FILES)

# The partner's extract is confidential and gitignored, so a clone without it
# must still run green. But a gate that silently skips is a gate that protects
# nothing: a partner could refactor the engine, see 443 tests pass, and never
# learn that parity broke.
#
# So: skipping is opt-in and loud. Set TCC_REQUIRE_PARITY=1 in CI and in
# any environment that HAS the fixtures, and a missing fixture becomes an error
# instead of a skip.
_REQUIRE_PARITY = os.environ.get("TCC_REQUIRE_PARITY", "").strip().lower() in {"1", "true", "yes"}

if _REQUIRE_PARITY and not _FIXTURES_PRESENT:
    raise RuntimeError(
        "TCC_REQUIRE_PARITY is set but the partner's reference payroll extract "
        f"is missing from {_SOURCE_DIR}. The parity gate cannot run, and skipping "
        "it would report a false pass. Stage the fixtures or unset the variable."
    )

# BA-01, BA-06 and the certified v7 figures now live in `tests/certified.py`,
# imported above, so the source-schema round-trip asserts the same values from
# the same definition rather than a second copy that could drift.


pytestmark = pytest.mark.skipif(
    not _FIXTURES_PRESENT,
    reason=(
        "the partner's reference payroll extract not present in this checkout. "
        "Set TCC_REQUIRE_PARITY=1 to make this an error instead of a skip."
    ),
)


def _bcs_rows(step1) -> list[dict]:
    """Map the reference run's collapsed rows into the Silver Record Layout shape.

    Both engines are fed the *same* rows so the comparison isolates calculation
    logic from ingestion. The production engine re-applies its own collapse,
    which is idempotent over already-collapsed input.
    """
    return [
        {
            "Tax_Year": row.pay_date.year,
            "Employee_ID": row.employee_id,
            "Worksite_ID": row.unit_id,
            "Job_Title": "",
            "Entity_FEIN": row.fein,
            "Pay_Period_Start": row.pay_period_start.isoformat(),
            "Pay_Period_End": row.pay_period_end.isoformat(),
            "Pay_Date": row.pay_date.isoformat(),
            "Pay_Frequency": row.pay_frequency_code,
            "Pay_Code": "Regular",
            "Hours_Worked": float(row.hours),
            "Gross_Wages": float(row.wages),
        }
        for row in step1.collapsed_rows
    ]


# `certified_pack()` is imported from tests/certified.py. Aliased so the
# existing call sites below read unchanged.
_certified_pack = certified_pack


@pytest.fixture(scope="module")
def reference():
    """The certified benchmark run — the answer the product must reproduce."""
    snapshot = TccPayrollAdapter(source_dir=_SOURCE_DIR).scan()
    return run_reference_step1(snapshot)


@pytest.fixture(scope="module")
def production(reference):
    """The same data through the engine the application actually calls."""
    rows = _bcs_rows(reference)
    pack = _certified_pack()
    common = {
        "tax_year": 2023,
        "analysis_start_month": date(2023, 8, 1),
        "pack": pack,
        "fiscal_window": FISCAL_WINDOW,
    }
    return {
        "min_max": run_min_max_method(rows, **common),
        "pay_period": run_pay_period_method(rows, **common),
    }


def _reference_eligible(reference, method: str) -> set[str]:
    source = reference.min_max if method == "min_max" else reference.pay_period
    return {employee_id for employee_id, row in source.items() if row.eligible}


def _production_eligible(production, method: str) -> set[str]:
    return {row["Employee_ID"] for row in production[method].eligible_employees}


def test_certified_floors_match_the_year_pack():
    """The TY2023 rule pack still carries the floors the certified run used.

    The engine resolves $636 from `rules/ga_jtc/2023.json` rather than from an
    assumption set [ADR-005], so an edit to that pack would move every number
    downstream. This is the tripwire.
    """
    assert_year_pack_agrees()


def test_population_matches(reference, production):
    """Both engines see the same employees after the BA-02 trim."""
    assert len(reference.common_totals) == CERTIFIED_EMPLOYEES
    assert len(production["min_max"].total_hours_and_wages) == CERTIFIED_EMPLOYEES


def test_totals_match(reference, production):
    """BA-05/BA-12 — the numerator is identical, to the cent.

    This is the control that proves the short-period rule stayed out of the
    numerator. If it drifts, every average downstream is wrong.
    """
    produced = {
        row["Employee_ID"]: (row["total_hours"], row["total_wages"])
        for row in production["min_max"].total_hours_and_wages
    }
    mismatches = [
        employee_id
        for employee_id, totals in reference.common_totals.items()
        if employee_id in produced
        and (
            abs(Decimal(str(produced[employee_id][0])) - totals.total_hours) > Decimal("0.01")
            or abs(Decimal(str(produced[employee_id][1])) - totals.total_wages) > Decimal("0.01")
        )
    ]
    assert not mismatches, f"{len(mismatches)} employees differ, e.g. {mismatches[:5]}"


def test_min_max_eligibility_matches(reference, production):
    """BA-11 + BA-12 — exclusive-day span over qualifying periods."""
    expected = _reference_eligible(reference, "min_max")
    actual = _production_eligible(production, "min_max")
    assert len(expected) == CERTIFIED_MIN_MAX_ELIGIBLE
    assert actual == expected, (
        f"production {len(actual)} vs certified {len(expected)}; "
        f"missing={sorted(expected - actual)[:5]} extra={sorted(actual - expected)[:5]}"
    )


def test_pay_period_eligibility_matches(reference, production):
    """BA-03 + BA-12 — summed actual spans over qualifying periods."""
    expected = _reference_eligible(reference, "pay_period")
    actual = _production_eligible(production, "pay_period")
    assert len(expected) == CERTIFIED_PAY_PERIOD_ELIGIBLE
    assert actual == expected, (
        f"production {len(actual)} vs certified {len(expected)}; "
        f"missing={sorted(expected - actual)[:5]} extra={sorted(actual - expected)[:5]}"
    )


def test_denominator_modes_are_distinguishable():
    """The rejected denominator stays reachable so historical runs replay.

    We do not use `frequency_code` — it is the approach that produced 447
    eligible against the partner's 659 — but a run recorded under it must reproduce
    exactly, or the audit promise fails. A calendar month separates the two
    cleanly: the constant says 4.33 weeks, the measured span says 4.43.
    """
    rows = [
        {
            "Tax_Year": 2023, "Employee_ID": "E1", "Worksite_ID": "U1",
            "Job_Title": "x", "Entity_FEIN": "f", "Pay_Code": "Regular",
            "Pay_Period_Start": "2023-08-01", "Pay_Period_End": "2023-08-31",
            "Pay_Date": "2023-09-05", "Hours_Worked": 160.0, "Gross_Wages": 8000.0,
        },
    ]

    def weeks_for(mode: str) -> float:
        pack = _certified_pack()
        pack.methodology = OneZeroMethodology(pay_period_denominator_mode=mode)
        result = run_pay_period_method(
            rows,
            tax_year=2023,
            analysis_start_month=date(2023, 8, 1),
            pack=pack,
            fiscal_window=FISCAL_WINDOW,
        )
        return result.all_averages[0]["weeks_worked"]

    assert weeks_for("frequency_code") == pytest.approx(52 / 12, abs=0.01)
    assert weeks_for("actual_span") == pytest.approx(31 / 7, abs=0.01)
