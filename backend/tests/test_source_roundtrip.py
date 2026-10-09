"""Round-trip gate: reference CSV -> FlexSchema -> BCS -> engine.

The partner will hand us their `intranet` schema, not the CSVs they exported. This
asserts that routing the reference dataset through that shape and back out is
**lossless** — the certified figures survive the projection.

If this fails, the Silver projection is dropping or corrupting something, and we
would find out with real client data instead of here.

    10,236 employees  ·  539 Min-Max eligible  ·  656 Pay Period eligible

Skipped when the confidential reference extract is absent. Set
`TCC_REQUIRE_PARITY=1` to make that an error instead — see
`tests/test_engine_parity_reference.py`.
"""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path

import pytest

from certified import (
    CERTIFIED_EMPLOYEES,
    CERTIFIED_MIN_MAX_ELIGIBLE,
    CERTIFIED_PAY_PERIOD_ELIGIBLE,
    FISCAL_WINDOW,
    certified_pack,
)
from data.source import (
    build_reference_source_dataset,
    source_to_bcs_rows,
    projection_controls,
)
from domain.calculation.onezero import run_min_max_method, run_pay_period_method

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_DIR = _BACKEND_ROOT / "data" / "payroll"
_SOURCE_FILES = ("One.csv", "Two.csv", "Three.csv", "Four.csv")
_FIXTURES_PRESENT = all((_SOURCE_DIR / n).exists() for n in _SOURCE_FILES)

if os.environ.get("TCC_REQUIRE_PARITY", "").strip().lower() in {"1", "true", "yes"}:
    if not _FIXTURES_PRESENT:
        raise RuntimeError(
            "TCC_REQUIRE_PARITY is set but the reference extract is missing "
            f"from {_SOURCE_DIR}; the source-schema round-trip gate cannot run."
        )

pytestmark = pytest.mark.skipif(
    not _FIXTURES_PRESENT,
    reason="the partner's reference payroll extract not present in this checkout",
)


@pytest.fixture(scope="module")
def dataset():
    """The reference dataset reshaped into the partner's source schema."""
    return build_reference_source_dataset()


@pytest.fixture(scope="module")
def bcs(dataset):
    """That source dataset projected back into the Silver Record Layout."""
    return source_to_bcs_rows(dataset)


@pytest.fixture(scope="module")
def results(bcs):
    pack = certified_pack()
    common = {
        "tax_year": 2023,
        "analysis_start_month": date(2023, 8, 1),
        "pack": pack,
        "fiscal_window": FISCAL_WINDOW,
    }
    return {
        "min_max": run_min_max_method(bcs, **common),
        "pay_period": run_pay_period_method(bcs, **common),
    }


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_source_dataset_is_well_formed(dataset):
    """Foreign keys resolve. A dangling reference here becomes a silent join
    failure in Silver, which is far harder to spot."""
    entity_ids = {e.entity_id for e in dataset.entities}
    location_ids = {loc.location_id for loc in dataset.locations}
    address_ids = {a.address_id for a in dataset.addresses}
    scz_ids = {s.state_county_zip_id for s in dataset.state_county_zips}
    pay_code_ids = {p.pay_code_id for p in dataset.pay_codes}

    assert dataset.entities, "no entities discovered"
    assert dataset.locations, "no locations discovered"

    for loc in dataset.locations:
        assert loc.entity_id in entity_ids
        assert loc.address_id in address_ids
    for addr in dataset.addresses:
        assert addr.state_county_zip_id in scz_ids
    for p in dataset.payroll:
        assert p.account_id == dataset.account.account_id
        assert p.entity_id in entity_ids
        assert p.location_id in location_ids
        assert p.pay_code_id in pay_code_ids


def test_every_payroll_row_carries_the_tenant(dataset):
    """`AccountId` is the tenant key and the partition column. A row without it
    is a row that cannot be isolated."""
    assert all(p.account_id == dataset.account.account_id for p in dataset.payroll)


def test_source_types_are_real_types(dataset):
    """The demo lakehouse stored dates as `M/D/YYYY` strings and currency as
    `'$2,061.19 '`. The source schema does not, and neither does this."""
    from decimal import Decimal

    sample = dataset.payroll[:200]
    assert all(isinstance(p.pay_period_start, date) for p in sample)
    assert all(isinstance(p.pay_period_end, date) for p in sample)
    assert all(p.pay_date is None or isinstance(p.pay_date, date) for p in sample)
    assert all(p.hours is None or isinstance(p.hours, Decimal) for p in sample)
    assert all(p.wages is None or isinstance(p.wages, Decimal) for p in sample)


# ---------------------------------------------------------------------------
# The projection is lossless
# ---------------------------------------------------------------------------


def test_projection_loses_no_rows(dataset, bcs):
    """Silver must not quietly drop payroll. Any drop has to be counted."""
    controls = projection_controls(dataset, bcs)
    assert controls["bcs_rows_out"] + controls["dropped_no_period_span"] == controls["payroll_rows_in"]
    assert controls["dropped_no_period_span"] == 0, "reference data should have no span-less rows"


def test_population_survives_the_round_trip(bcs, results):
    assert len({r["Employee_ID"] for r in bcs}) == CERTIFIED_EMPLOYEES
    assert len(results["min_max"].total_hours_and_wages) == CERTIFIED_EMPLOYEES


def test_min_max_survives_the_round_trip(results):
    """BA-11 + BA-12 through the source shape."""
    assert len(results["min_max"].eligible_employees) == CERTIFIED_MIN_MAX_ELIGIBLE


def test_pay_period_survives_the_round_trip(results):
    """BA-03 + BA-12 through the source shape."""
    assert len(results["pay_period"].eligible_employees) == CERTIFIED_PAY_PERIOD_ELIGIBLE


def test_eligible_sets_are_identical_to_the_direct_path(results):
    """Counts matching is not enough — the same *employees* must qualify.

    Two different populations of 539 would pass a count assertion and be wrong.
    """
    from tools.reference_source import TccPayrollAdapter
    from tools.reference_step1 import run_reference_step1

    reference = run_reference_step1(TccPayrollAdapter(source_dir=_SOURCE_DIR).scan())
    expected_mm = {e for e, r in reference.min_max.items() if r.eligible}
    expected_pp = {e for e, r in reference.pay_period.items() if r.eligible}

    actual_mm = {r["Employee_ID"] for r in results["min_max"].eligible_employees}
    actual_pp = {r["Employee_ID"] for r in results["pay_period"].eligible_employees}

    assert actual_mm == expected_mm, (
        f"Min-Max differs: missing={sorted(expected_mm - actual_mm)[:5]} "
        f"extra={sorted(actual_mm - expected_mm)[:5]}"
    )
    assert actual_pp == expected_pp, (
        f"Pay Period differs: missing={sorted(expected_pp - actual_pp)[:5]} "
        f"extra={sorted(actual_pp - expected_pp)[:5]}"
    )


# ---------------------------------------------------------------------------
# Fields the source shape unlocks
# ---------------------------------------------------------------------------


def test_county_is_reachable_from_a_payroll_row(dataset):
    """County drives Georgia's tier, which drives credit VALUE — one of the four
    inputs missing from dollar certification. Prove the join path exists."""
    addr_by_id = {a.address_id: a for a in dataset.addresses}
    scz_by_id = {s.state_county_zip_id: s for s in dataset.state_county_zips}
    loc_by_id = {loc.location_id: loc for loc in dataset.locations}

    p = dataset.payroll[0]
    location = loc_by_id[p.worksite_location_id or p.location_id]
    address = addr_by_id[location.address_id]
    county = scz_by_id[address.state_county_zip_id]
    assert county.county_name
    assert county.state_abbr == "GA"


def test_fiscal_window_comes_from_the_rules_table(dataset):
    """BA-01 is per-client configuration. In the source it lives on
    `Entity.FiscalYearRulesId`, not in payroll — which is the whole point."""
    rules = {r.fiscal_year_rules_id: r for r in dataset.fiscal_year_rules}
    entity = dataset.entities[0]
    assert entity.fiscal_year_rules_id in rules
    rule = rules[entity.fiscal_year_rules_id]
    assert (rule.fiscal_year_begin, rule.fiscal_year_end) == FISCAL_WINDOW


def test_inferred_lookups_are_flagged_as_inferred(dataset):
    """`PayFrequency` and `EntityFiscalYearRules` were never supplied by
    the partner. Anything we stood up in their place must say so, or someone will
    later cite our guess back to us as their specification."""
    assert dataset.pay_frequencies, "pay frequency lookup missing"
    assert all(f.inferred for f in dataset.pay_frequencies)
    assert all(r.inferred for r in dataset.fiscal_year_rules)
