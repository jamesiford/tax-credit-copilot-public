"""The public parity gate's pinned figures, in one place. [WL-11, D21]

Computed ONCE from the committed synthetic dataset
(`backend/data/payroll_pay_periods.csv`) through the SAME production engine
(`domain.calculation.onezero`) the private gate (`tests/certified.py`,
`test_engine_parity_reference.py`) asserts against. There is no independent
second implementation for this dataset — nobody hand-computed MeridianCore's
eligibility in Access — so unlike the private gate this is a REGRESSION pin,
not a cross-implementation agreement. It still catches the thing that matters
most for a public clone: the engine silently producing a different answer on
data anyone can see.

**Never edit these to make a test pass.** A change that moves them is either a
genuine improvement to the engine (which needs re-pinning deliberately, in its
own commit, with the reason stated) or a regression. It is never a test that
needs updating.

This module is deliberately not named `test_*`, so pytest does not collect it.
"""
from __future__ import annotations

from datetime import date

from domain.calculation.onezero import OneZeroMethodology, OneZeroPack

# The synthetic dataset's Georgia rows, Tax Year 2024, under a calendar-year
# fiscal window — the one reading nobody can dispute, since the dataset has no
# per-client fiscal rule of its own to apply instead (unlike the reference
# client's BA-01 window).
FISCAL_WINDOW: tuple[date, date] = (date(2024, 1, 1), date(2024, 12, 31))
ANALYSIS_START_MONTH = date(2024, 1, 1)

# rules/ga_jtc/2024.json's one_zero block, as literals for the same reason
# tests/certified.py keeps MIN_WEEKLY_HOURS/MIN_WEEKLY_WAGES literal: so an
# edit to the pack cannot silently move this gate's pinned figures along with
# it. `assert_year_pack_agrees` is the tripwire.
MIN_WEEKLY_HOURS = 35.0
MIN_WEEKLY_WAGES = 686.0
CERTIFIED_SYNTHETIC_PROGRAM_CODE = "GA_JTC"
CERTIFIED_SYNTHETIC_TAX_YEAR = 2024

# The synthetic gate's result: Georgia rows only, Tax Year 2024.
CERTIFIED_SYNTHETIC_EMPLOYEES = 81
CERTIFIED_SYNTHETIC_MIN_MAX_ELIGIBLE = 51
CERTIFIED_SYNTHETIC_PAY_PERIOD_ELIGIBLE = 49


def assert_synthetic_year_pack_agrees() -> None:
    """Fail if the TY2024 GA JTC pack no longer matches the pinned floors."""
    from tools.credit_math import resolve_statutory_floors

    floors = resolve_statutory_floors(CERTIFIED_SYNTHETIC_PROGRAM_CODE, CERTIFIED_SYNTHETIC_TAX_YEAR)
    if (floors.min_weekly_hours, floors.min_weekly_wages) != (MIN_WEEKLY_HOURS, MIN_WEEKLY_WAGES):
        raise AssertionError(
            f"rules/ga_jtc/2024.json says {floors.min_weekly_hours} hrs / "
            f"${floors.min_weekly_wages}, but the synthetic gate used "
            f"{MIN_WEEKLY_HOURS} hrs / ${MIN_WEEKLY_WAGES}. The pack was edited. "
            f"Revert it, or re-pin the synthetic figures deliberately."
        )


def certified_synthetic_pack() -> OneZeroPack:
    """A GA JTC pack carrying the methodology the synthetic gate used.

    Every value is spelled out even though each is the dataclass default, for
    the same reason `tests/certified.py:certified_pack` does: a future edit to
    the defaults then fails this loudly rather than silently moving the pin.
    """
    return OneZeroPack(
        min_weekly_hours=MIN_WEEKLY_HOURS,
        min_weekly_wages=MIN_WEEKLY_WAGES,
        wage_basis="all_remuneration",
        geographic_granularity="unit",
        pt_aggregation=False,
        headcount_unit_field="Worksite_ID",
        citation="O.C.G.A. 48-7-40",
        tax_year=CERTIFIED_SYNTHETIC_TAX_YEAR,
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
