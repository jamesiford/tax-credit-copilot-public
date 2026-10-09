"""The certified figures, in one place.

These are the numbers reconciled with Experian between 30 July and 24 August
2026, and they are asserted from more than one test module — the direct parity
gate (`test_engine_parity_reference.py`) and the FlexSchema round-trip
(`test_flex_roundtrip.py`).

They live here so there is exactly one definition. Two copies would eventually
disagree, and the copy that was not updated would keep passing.

**Never edit these to make a test pass.** A change that moves them is wrong
until Experian says otherwise. See `docs/data/CALCULATION-RULES-V7.md`.

This module is deliberately not named `test_*`, so pytest does not collect it.
"""
from __future__ import annotations

from datetime import date

from domain.calculation.onezero import OneZeroMethodology, OneZeroPack

# BA-01 — Experian's 53-week payroll calendar for the reference client. Per-client
# configuration; no month-end fiscal year can express it.
FISCAL_WINDOW: tuple[date, date] = (date(2023, 7, 28), date(2024, 8, 2))

# BA-06 — Tax Year 2023 Georgia floors: 35 hrs/wk, and the DOL 2022 average
# weekly wage for Glascock County ($33,072 / 52 = $636).
#
# These stay literal on purpose. From v8 the engine resolves them from
# `backend/rules/ga_jtc/2023.json` [ADR-005], and if this module resolved them
# the same way, editing that pack would quietly move the certified result along
# with it and the gate would keep passing. Instead the literal is the anchor and
# `assert_year_pack_agrees()` checks the pack against it.
MIN_WEEKLY_HOURS = 35.0
MIN_WEEKLY_WAGES = 636.0
CERTIFIED_PROGRAM_CODE = "GA_JTC"
CERTIFIED_TAX_YEAR = 2023


def assert_year_pack_agrees() -> None:
    """Fail if the TY2023 rule pack no longer matches the certified floors.

    The engine reads the pack; this module holds the reconciled figures. When
    they diverge, one of them is wrong — and it is not this one until Experian
    says so.
    """
    from tools.credit_math import resolve_statutory_floors

    floors = resolve_statutory_floors(CERTIFIED_PROGRAM_CODE, CERTIFIED_TAX_YEAR)
    if (floors.min_weekly_hours, floors.min_weekly_wages) != (
        MIN_WEEKLY_HOURS,
        MIN_WEEKLY_WAGES,
    ):
        raise AssertionError(
            f"rules/ga_jtc/2023.json says {floors.min_weekly_hours} hrs / "
            f"${floors.min_weekly_wages}, but the certified run used "
            f"{MIN_WEEKLY_HOURS} hrs / ${MIN_WEEKLY_WAGES}. The pack was edited. "
            f"Revert it — the certified figures are not adjustable."
        )


# The certified v7 result on the reference dataset.
CERTIFIED_EMPLOYEES = 10_236
CERTIFIED_MIN_MAX_ELIGIBLE = 539
CERTIFIED_PAY_PERIOD_ELIGIBLE = 656


def certified_pack() -> OneZeroPack:
    """A GA JTC pack carrying the certified v7 methodology.

    Every methodology value is spelled out even though each is the dataclass
    default. That is deliberate: a future edit to the defaults then fails this
    loudly rather than silently moving the certified numbers.
    """
    return OneZeroPack(
        min_weekly_hours=MIN_WEEKLY_HOURS,
        min_weekly_wages=MIN_WEEKLY_WAGES,
        wage_basis="all_remuneration",
        geographic_granularity="unit",
        pt_aggregation=False,
        headcount_unit_field="Worksite_ID",
        citation="O.C.G.A. 48-7-40",
        tax_year=2023,
        methodology=OneZeroMethodology(
            minimum_pay_period_days=7,
            short_periods_excluded_from_numerator=False,
            pay_period_denominator_mode="actual_span",
            min_max_span_mode="exclusive_days",
            count_zero_hour_periods=True,
            average_decimals=2,
            exclude_off_cycle_periods=False,
        ),
    )
