"""The One/Zero Base Calculation engine.

This is the deterministic Python implementation of the partner's statutory Base
Calculation Service (BCS) — the "1/0" or "One/Zero" report that almost every
state Jobs Tax Credit boils down to. Its documented sources:

  - the 7-step Pay Period Method (preferred)
  - the 6-step Min Max Method (fallback for messy payroll)
  - the partner's business framing of the Base Calculation Service and its
    Silver Record Layout
  - the GA JTC One/Zero methodology overview — visual / worked examples

Both methods run against the same input shape (Silver Record Layout, 16 fields;
prototype CSV ships only the 11 required ones in `data/payroll_pay_periods.csv`).

Eligibility floors are pulled from each rule pack's `one_zero` block — for
GA JTC that's >=35 hrs/wk avg AND >=$680/wk avg (statewide; future packs may
override per county, per pack).

The engine NEVER mutates input rows; every step returns a fresh structure.
Every step records a trail row via `domain.calculation.trail.TrailRecorder` so the
existing Evidence anatomy / Audit lifecycle UI surfaces the calculation
without modification.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, fields
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .trail import TrailRecorder, current_recorder


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class OneZeroMethodology:
    """How the calculation is *measured*, as distinct from what the statute *requires*.

    `OneZeroPack` carries the statutory parameters — floors, wage basis, part-time
    bands — which genuinely differ by state. This carries the methodology, which
    does not: a Min-Max span is measured the same way in Georgia as in Tennessee.

    Every default below is the v7 rule set certified against the partner between
    30 July and 24 August 2026. The derivation, with the source quote behind each
    rule, is in `docs/data/CALCULATION-RULES-V7.md`. A rule pack may override any
    of them, but only where a state genuinely dictates otherwise.
    """

    # BA-12. Pay periods shorter than this are not real pay periods. The partner,
    # 2026-08-20: "you get a lot of these garbagey pay periods that
    # come through - one day pay periods, two day pay periods... if you include
    # those, you're going to potentially aggregate up to way more than 52 weeks."
    minimum_pay_period_days: int = 7

    # BA-12, the asymmetry. Short periods leave the denominator but their hours
    # and wages stay in the numerator, because the money was genuinely earned:
    # "I go back to the stored payroll file where I aggregated all wages paid,
    # all hours worked, irrespective of good or bad pay periods." Setting this
    # True reproduces the error the partner identified in their own 12 August file.
    short_periods_excluded_from_numerator: bool = False

    # BA-03. Each period contributes its own span, not a constant looked up from
    # the source frequency code. The codes do not behave as documented - every
    # code-4 period in the partner's extract runs the 16th to the 31st - and the
    # literal reading yields 447 eligible against the partner's 659.
    pay_period_denominator_mode: str = "actual_span"  # 'actual_span' | 'frequency_code'

    # BA-11. One Zero Min Max.docx Step 2: "count the number of days between the
    # two and divide by 7" - no inclusive-day adjustment, so a full-year weekly
    # employee lands on 51.86 weeks rather than 52.00. Confirmed against the partner's
    # reported weeks for eight of the nine employees they detailed.
    min_max_span_mode: str = "exclusive_days"  # 'exclusive_days' | 'inclusive_days'

    # BA-05. Zero-hour wage rows are real payroll facts and stay in the totals.
    count_zero_hour_periods: bool = True

    # BA-06. Averages round to two decimals half-up, and the rounded value is
    # what the thresholds test. This admits an employee at 34.9998 hours, which
    # the partner endorsed: "why not include them? I'm a big fan of giving the auditors
    # things to throw out."
    average_decimals: int = 2

    # BA-09. Report violations; never silently cap a denominator.
    maximum_weeks_without_review: float = 53.0

    # Legacy off-cycle heuristic: drop a pay period whose employee count is
    # below half the median for its cadence. This predates BA-12 and tried to
    # solve the same problem less defensibly - it is population-relative, so
    # the same employee's period can qualify or not depending on who else was
    # paid that week. BA-12's day-count test supersedes it, so the certified
    # path leaves this off and includes every qualifying period.
    exclude_off_cycle_periods: bool = False

    @classmethod
    def from_pack_json(cls, block: dict[str, Any] | None) -> "OneZeroMethodology":
        """Build from a rule pack's optional `methodology` block.

        Absent or partial blocks inherit the certified defaults, so the ten
        existing packs pick up correct behaviour without being edited.

        Unknown keys raise rather than being dropped. A typo like
        `minimum_pay_period_day` would otherwise leave the pack silently running
        certified defaults while its author believed it was overridden — and the
        only symptom would be a wrong number on a filed return.
        """
        if not block:
            return cls()
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(block) - known)
        if unknown:
            raise ValueError(
                f"unknown one_zero.methodology key(s): {', '.join(unknown)}. "
                f"Valid keys: {', '.join(sorted(known))}"
            )
        invalid = []
        if block.get("pay_period_denominator_mode", "actual_span") not in (
            "actual_span", "frequency_code",
        ):
            invalid.append("pay_period_denominator_mode")
        if block.get("min_max_span_mode", "exclusive_days") not in (
            "exclusive_days", "inclusive_days",
        ):
            invalid.append("min_max_span_mode")
        if int(block.get("minimum_pay_period_days", 7)) < 0:
            invalid.append("minimum_pay_period_days")
        if invalid:
            raise ValueError(f"invalid one_zero.methodology value(s): {', '.join(invalid)}")
        return cls(**block)


@dataclass
class OneZeroPack:
    """Eligibility parameters lifted from a rule pack's `one_zero` block.

    Loose validation only - the rule-pack JSON is the source of truth; the
    engine just consumes already-validated values.

    The base floor fields (`min_weekly_hours`/`min_weekly_wages`) are the
    *resolved* values for a given tax year — `credit_math.load_pack_one_zero`
    applies any `thresholds_by_year` override before constructing the pack.
    """
    min_weekly_hours: float
    min_weekly_wages: float
    wage_basis: str               # 'regular' | 'all_remuneration'
    geographic_granularity: str   # 'unit' | 'county' | 'statewide'
    pt_aggregation: bool          # part-time hour aggregation allowed?
    headcount_unit_field: str     # column name in input rows (default Worksite_ID)
    citation: str                 # statutory cite for trail rows
    # [H2] CALC-03 — part-time band -> fractional headcount weight (SC: 20-32 hrs = 0.5).
    pt_band_hours: tuple[float, float] | None = None
    pt_weight: float | None = None
    # [H3] CALC-04 — state-stipulated measuring date ('last_day' default).
    measuring_date: str = "last_day"
    # [I2] CALC-06 — entity (FEIN) combination treatment.
    entity_combination: str = "permitted"  # 'required' | 'permitted' | 'prohibited'
    # [L5] CALC-11 — pay-code inclusion/suppression for the weekly-wage test.
    # included_pay_codes None = include all; excluded wins over included.
    included_pay_codes: tuple[str, ...] | None = None
    excluded_pay_codes: tuple[str, ...] | None = None
    # Which tax year these floors were resolved for (None = default/flat).
    tax_year: int | None = None
    # How the calculation is measured. Statutory parameters above vary by state;
    # these do not. Defaults are the v7 rules certified against the partner — see
    # `docs/architecture/ENGINE-CONVERGENCE.md` for why this seam exists.
    methodology: OneZeroMethodology = field(default_factory=OneZeroMethodology)


@dataclass
class OneZeroResult:
    """Output of either method. Shaped so Pay Period and Min Max are diffable."""
    method: str  # 'pay_period' | 'min_max'
    tax_year: int
    analysis_start_month: date
    months: list[date]                           # 12 month-end dates in order
    total_hours_and_wages: list[dict]            # per-employee totals
    eligible_employees: list[dict]               # employees passing both floors
    employee_unit_matrix: list[dict]             # one row per (employee, unit, segment)
    summary: list[dict]                          # per-unit-per-month totals
    average_headcount: dict[str, float]          # unit_id -> 12-month average
    annual_average: float                        # mean across all units
    flags: list[dict] = field(default_factory=list)  # data-quality issues
    all_averages: list[dict] = field(default_factory=list)  # per-EE avg incl. ineligible (drill-in)


# ---------------------------------------------------------------------------
# Pre-processing (common to both methods)
# ---------------------------------------------------------------------------


def _parse_iso(s: str | date) -> date:
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s)[:10])


def _coerce_float(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    return float(v)


def _round_half_up(value: float, places: int = 2) -> float:
    """BA-06 — round half away from zero, as Access and Excel do.

    Python's built-in `round` is banker's rounding: `round(0.125, 2)` gives
    0.12, where the partner's Access query gives 0.13. On a $636 wage floor that is
    the difference between eligible and not for anyone landing exactly on a
    half-cent, so the convention has to match theirs.
    """
    quant = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def fiscal_year_of(pay_date: date, fiscal_year_end_month: int = 12) -> int:
    """[H4] CALC-05 — fiscal year (labelled by the year it ENDS) for a pay date.

    Calendar year (`fiscal_year_end_month == 12`) returns `pay_date.year`,
    matching the original calendar-year behaviour. For a March year-end
    (the partner's test case, `fiscal_year_end_month == 3`) a pay date in
    April 2024-March 2025 belongs to FY2025.
    """
    if fiscal_year_end_month == 12:
        return pay_date.year
    if pay_date.month <= fiscal_year_end_month:
        return pay_date.year
    return pay_date.year + 1


def fiscal_window_start(tax_year: int, fiscal_year_end_month: int = 12) -> date:
    """[H4] CALC-05 — first day of the 12-month analysis window for a fiscal year.

    Calendar year -> Jan 1 of the tax year. March year-end -> April 1 of the
    prior calendar year (FY2025 = Apr 2024 .. Mar 2025).
    """
    if fiscal_year_end_month == 12:
        return date(tax_year, 1, 1)
    start_month = fiscal_year_end_month % 12 + 1
    start_year = tax_year - 1 if start_month > 1 else tax_year
    return date(start_year, start_month, 1)


def preprocess(
    rows: list[dict],
    *,
    tax_year: int,
    fiscal_year_end_month: int = 12,
    fiscal_window: tuple[date, date] | None = None,
    methodology: OneZeroMethodology | None = None,
    recorder: TrailRecorder | None = None,
) -> list[dict]:
    """Pre-flight cleanup before either method runs.

    Per the source docs:
      1. Drop rows whose PaycheckDate falls outside the analysis window (the GA
         xlsx callout: "Any hours worked or wages earned that show up on a
         different tax year's pay stub should not be included"). [H4] CALC-05:
         "tax year" is the configurable FISCAL year, bucketed by pay date —
         calendar year is the `fiscal_year_end_month == 12` default.
      2. Collapse duplicate (Employee_ID, Worksite_ID, PPS, PPE) records by
         summing hours + wages (xlsx callout: "Pay periods with the same PPS
         and PPE should be collapsed into 1 record").
      3. Optionally drop pay periods with zero hours (xlsx: "Pay periods with
         no hours can usually be eliminated as they are bonuses").

    BA-01: `fiscal_window` overrides the derived year when a client's fiscal
    year does not land on a month boundary. The partner's reference dataset runs
    2023-07-28 to 2024-08-02 — a 53-week payroll calendar that no
    `fiscal_year_end_month` can express. This is per-client configuration and
    is not derivable from payroll.

    BA-05: the certified rule KEEPS zero-hour rows, because a zero-hour wage
    row is a real payroll fact and its wages belong in the numerator. Set
    `count_zero_hour_periods=False` on the methodology to restore the older
    drop-them behaviour.

    Returns a NEW list. Records the step in the trail recorder if one is active.
    """
    if recorder is None:
        recorder = current_recorder()
    if methodology is None:
        methodology = OneZeroMethodology()

    in_count = len(rows)

    # [H4] / BA-01 — trim on paycheck date. An explicit window wins over the
    # derived fiscal year.
    if fiscal_window is not None:
        window_start, window_end = fiscal_window
        tax_year_rows = [
            r for r in rows
            if window_start <= _parse_iso(r["Pay_Date"]) <= window_end
        ]
    else:
        tax_year_rows = [
            r for r in rows
            if fiscal_year_of(_parse_iso(r["Pay_Date"]), fiscal_year_end_month) == tax_year
        ]
    dropped_off_year = in_count - len(tax_year_rows)

    # Collapse duplicate (EE, Unit, PPS, PPE).
    grouped: dict[tuple, dict] = {}
    for r in tax_year_rows:
        key = (r["Employee_ID"], r["Worksite_ID"], r["Pay_Period_Start"], r["Pay_Period_End"])
        if key in grouped:
            existing = grouped[key]
            existing["Hours_Worked"] = round(_coerce_float(existing["Hours_Worked"]) + _coerce_float(r["Hours_Worked"]), 2)
            existing["Gross_Wages"] = round(_coerce_float(existing["Gross_Wages"]) + _coerce_float(r["Gross_Wages"]), 2)
        else:
            grouped[key] = dict(r)
            grouped[key]["Hours_Worked"] = _coerce_float(r["Hours_Worked"])
            grouped[key]["Gross_Wages"] = _coerce_float(r["Gross_Wages"])
    collapsed = list(grouped.values())
    collapsed_count = len(tax_year_rows) - len(collapsed)

    # BA-05 — zero-hour rows are retained by default.
    if methodology.count_zero_hour_periods:
        out = collapsed
        dropped_zero_hours = 0
    else:
        out = [r for r in collapsed if _coerce_float(r["Hours_Worked"]) > 0]
        dropped_zero_hours = len(collapsed) - len(out)

    if recorder:
        recorder.record(
            step="onezero.preprocess",
            inputs={"rows_in": in_count, "tax_year": tax_year},
            formula=(
                "filter(PaycheckDate in window) -> collapse_by(EE,Unit,PPS,PPE)"
                + ("" if methodology.count_zero_hour_periods else " -> drop hours==0")
            ),
            output={
                "rows_out": len(out),
                "dropped_off_tax_year": dropped_off_year,
                "collapsed_duplicates": collapsed_count,
                "dropped_zero_hours": dropped_zero_hours,
            },
            citation="BCS business-framing doc; GA xlsx pre-processing notes; BA-01, BA-02, BA-05",
        )
    return out


# ---------------------------------------------------------------------------
# Shared helpers (eligibility + monthly column logic)
# ---------------------------------------------------------------------------


def _twelve_month_ends(start_month: date) -> list[date]:
    """Return the last calendar day of each of 12 months starting at `start_month`."""
    out: list[date] = []
    y, m = start_month.year, start_month.month
    for _ in range(12):
        # Last day of month: first of next month minus one day.
        if m == 12:
            last = date(y, 12, 31)
            y2, m2 = y + 1, 1
        else:
            last = date(y, m + 1, 1) - timedelta(days=1)
            y2, m2 = y, m + 1
        out.append(last)
        y, m = y2, m2
    return out


def first_measurable_month(rows: list[dict], window: tuple[date, date]) -> date:
    """The month the twelve measuring dates should start at, for a given window.

    A fiscal year that opens mid-month opens on a **stub**: the partner's reference
    client runs 2023-07-28 to 2024-08-02, but its earliest pay period starts
    2023-08-01, so not one row spans 2023-07-31. Starting the twelve months at
    the window's own month therefore burns Month 1 on a date no payroll can
    reach — every employee scores zero — and pushes the real final month
    (July 2024) off the end of the matrix entirely. On the reference client that
    understated the Min-Max annual average by 35 jobs, 410.13 -> 375.53.

    OZ-01 already worked around this for the sealed run by pinning the window to
    August-July by hand. This derives the same answer instead: walk the candidate
    month-ends and take the first one a pay period actually spans. A client whose
    year opens on the first of a month is unaffected, because that month's end is
    covered and the walk stops immediately.
    """
    window_start, window_end = window
    cursor = date(window_start.year, window_start.month, 1)
    spans = _period_spans(rows)

    while cursor <= window_end:
        month_end = _twelve_month_ends(cursor)[0]
        if _spanned(month_end, spans):
            return cursor
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)

    # No month-end is covered at all. Nothing to rescue; the caller's own window
    # is still the most defensible starting point.
    return window_start


def unreachable_months(rows: list[dict], months: list[date]) -> list[int]:
    """Positions where no pay period reaches the measuring date at all.

    A month nothing spans scores zero for every employee, and that zero looks
    exactly like a location that emptied out. It is not the same fact and must
    not be read as one: the reference client's Month 12 target, 2024-07-31, is
    reached by nothing (the latest pay-period end is 2024-07-26) and produces a
    number only because `_adjusted_target_for_month` retargets to the employee's
    last pay-period end. A client whose final period ends on or before the 15th
    gets no such rescue and would publish a confident zero.
    """
    spans = _period_spans(rows)
    return [index for index, month_end in enumerate(months) if not _spanned(month_end, spans)]


def _period_spans(rows: list[dict]) -> list[tuple[date, date]]:
    return [
        (_parse_iso(r["Pay_Period_Start"]), _parse_iso(r["Pay_Period_End"]))
        for r in rows
    ]


def _spanned(target: date, spans: list[tuple[date, date]]) -> bool:
    return any(start <= target <= end for start, end in spans)


def _adjusted_target_for_month(month_end: date, last_ppe_in_range: date, is_month_12: bool) -> date:
    """Apply the Month 12 special rule.

    From both prompt docs:
      "If the employee's Last PayPeriodEnd falls in Month 12 and the day is
       > 15, use that date as the target date instead of the month-end.
       Otherwise, use the last day of the month."
    """
    if is_month_12 and last_ppe_in_range.month == month_end.month and last_ppe_in_range.year == month_end.year and last_ppe_in_range.day > 15:
        return last_ppe_in_range
    return month_end


def _measuring_date_for_month(month_end: date, measuring_date: str) -> date:
    """[H3] CALC-04 — resolve the state-stipulated monthly measuring date.

    Default ('last_day') is the last calendar day of the month. A state whose
    rules differ can stipulate a numeric day-of-month (e.g. '15'); the engine
    clamps it to the month length. The Month-12 special rule is layered on top
    of whatever this returns.
    """
    if measuring_date in (None, "", "last_day"):
        return month_end
    try:
        day = int(measuring_date)
    except (TypeError, ValueError):
        return month_end
    day = max(1, min(day, month_end.day))
    return date(month_end.year, month_end.month, day)


def _pay_code_allowed(pay_code: str, pack: OneZeroPack) -> bool:
    """[L5] CALC-11 — is this pay code counted toward the weekly-wage test?

    Excluded codes (e.g. mileage / expense reimbursement) win over included.
    `included_pay_codes is None` means "include everything".
    """
    if pack.excluded_pay_codes and pay_code in pack.excluded_pay_codes:
        return False
    if pack.included_pay_codes and pay_code not in pack.included_pay_codes:
        return False
    return True


def apply_pay_code_policy(rows: list[dict], pack: OneZeroPack) -> list[dict]:
    """[L5] CALC-11 — drop pay-period rows whose pay code is suppressed for the
    weekly-wage test (e.g. Georgia counts all remuneration but excludes mileage).

    When the pack has no policy (or every row's code is allowed — the synthetic
    dataset is Regular-only) this returns the rows unchanged, so the established
    demo numbers do not move. Proven by the dedicated fixture test.
    """
    if not pack.included_pay_codes and not pack.excluded_pay_codes:
        return rows
    return [r for r in rows if _pay_code_allowed(str(r.get("Pay_Code", "Regular")), pack)]


def _classify_eligibility(row: dict, pack: OneZeroPack) -> tuple[float, bool, bool]:
    """[H1][H2] CALC-03 — classify one employee against the eligibility floors.

    Returns (weight, passed_hours, passed_wages):
      - weight 1.0  : meets the full weekly-hours floor AND the weekly-wage test
      - weight pt_weight (e.g. 0.5) : within the part-time band (SC 20-32 hrs)
                       AND passes the wage test
      - weight 0.0  : ineligible

    `passed_hours` reflects the FULL hours threshold (not the PT band) so the
    per-employee audit row is honest about which test the employee cleared.
    A state with `min_weekly_wages == 0` has no wage test (SC), so `passed_wages`
    is trivially True there.
    """
    h = row["avg_weekly_hours"]
    w = row["avg_weekly_wages"]
    passed_wages = w + 1e-9 >= pack.min_weekly_wages
    passed_hours = h + 1e-9 >= pack.min_weekly_hours
    if passed_hours and passed_wages:
        return 1.0, passed_hours, passed_wages
    # [H2] Part-time band -> fractional weight (e.g. SC 20-32 hrs counted as 0.5).
    if pack.pt_band_hours and pack.pt_weight and passed_wages:
        lo, _hi = pack.pt_band_hours
        if lo - 1e-9 <= h < pack.min_weekly_hours:
            return float(pack.pt_weight), passed_hours, passed_wages
    return 0.0, passed_hours, passed_wages


def _eligibility_filter(averages: list[dict], pack: OneZeroPack) -> list[dict]:
    """Annotate every employee with its eligibility test outcomes and return
    only those with a non-zero headcount weight.

    [H1] CALC-03 "test outcomes exposed per employee for audit": each row is
    annotated in place with `passed_hours`, `passed_wages`, `weight`, and
    `eligible` so the returned eligible list carries the booleans the Evidence
    trail / per-employee audit surfaces.
    """
    out = []
    for row in averages:
        if row["weeks_worked"] <= 0:
            row["weight"] = 0.0
            row["passed_hours"] = False
            row["passed_wages"] = False
            row["eligible"] = False
            continue
        weight, passed_hours, passed_wages = _classify_eligibility(row, pack)
        row["weight"] = weight
        row["passed_hours"] = passed_hours
        row["passed_wages"] = passed_wages
        row["eligible"] = weight > 0
        if weight > 0:
            out.append(row)
    return out


# ---------------------------------------------------------------------------
# Pay Period Method (preferred)
# ---------------------------------------------------------------------------


def _infer_frequency(period_days: int) -> str:
    """Infer pay-cycle type from period length in days."""
    if 5 <= period_days <= 8:
        return "weekly"
    if 12 <= period_days <= 16:
        return "biweekly"
    if 14 <= period_days <= 17:
        return "semimonthly"
    if 28 <= period_days <= 32:
        return "monthly"
    # Default catch-all
    return f"days_{period_days}"


def _detect_major_pay_periods(rows: list[dict]) -> dict[tuple[str, str, str], bool]:
    """For each (PPS, PPE, frequency_bucket) tuple, decide if it's a 'major'
    pay period — a regular pay-cycle period that includes a majority of the
    employees in that cycle. Off-cycle bonus runs / one-off corrections
    typically include very few employees and are excluded.

    Heuristic (matches the partner's prose "majority of employees within that pay
    cycle type"): for each frequency bucket, find the median employee count
    across distinct (PPS, PPE) groups; periods with >= 50% of the median count
    are major. Bonus runs typically have <10% so they fall away naturally.
    Returns: {(PPS, PPE, frequency): is_major}
    """
    # Group rows by (PPS, PPE) -> set of unique employees, and tag a frequency.
    by_period: dict[tuple[str, str], set[str]] = defaultdict(set)
    period_days: dict[tuple[str, str], int] = {}
    for r in rows:
        pps, ppe = r["Pay_Period_Start"], r["Pay_Period_End"]
        days = (_parse_iso(ppe) - _parse_iso(pps)).days + 1
        period_days[(pps, ppe)] = days
        by_period[(pps, ppe)].add(r["Employee_ID"])

    freq_buckets: dict[str, list[tuple[tuple[str, str], int]]] = defaultdict(list)
    for key, ees in by_period.items():
        freq = _infer_frequency(period_days[key])
        freq_buckets[freq].append((key, len(ees)))

    is_major: dict[tuple[str, str, str], bool] = {}
    for freq, items in freq_buckets.items():
        counts = sorted(c for _, c in items)
        median = counts[len(counts) // 2] if counts else 0
        threshold = max(1, median // 2)
        for (pps, ppe), c in items:
            is_major[(pps, ppe, freq)] = c >= threshold
    return is_major


def _frequency_weeks_per_period(freq: str) -> float:
    """Weeks implied by a frequency label.

    Retained for `pay_period_denominator_mode == 'frequency_code'` so historical
    runs replay, but it is NOT the certified path. Testing against the partner's
    extract showed the source frequency codes do not behave as documented -
    every code-4 period runs the 16th to the 31st, i.e. semi-monthly - and the
    literal reading returns 447 eligible against the partner's 659. See BA-03 in
    `docs/data/CALCULATION-RULES-V7.md`.
    """
    if freq == "weekly":
        return 1.0
    if freq == "biweekly":
        return 2.0
    if freq == "semimonthly":
        return 52 / 24  # ~2.167
    if freq == "monthly":
        return 52 / 12  # ~4.333
    return 1.0


def _period_days(row: dict) -> int:
    """Inclusive day count of a pay period: a Mon-Sun week is 7 days, not 6."""
    return (_parse_iso(row["Pay_Period_End"]) - _parse_iso(row["Pay_Period_Start"])).days + 1


def qualifies_as_pay_period(row: dict, methodology: OneZeroMethodology) -> bool:
    """BA-12 — is this a real pay period, or a payroll artefact?

    Off-cycle corrections, terminal cheques and bonus runs arrive as one- and
    two-day periods. Counting them inflates the denominator past 52 weeks and
    depresses the weekly average, so they are excluded from the *denominator*.
    Their hours and wages remain in the numerator - see the caller in each
    method - because the money was genuinely earned.

    The partner, 2026-08-20: "you get a lot of these garbagey pay periods
    that come through... if you include those, you're going to potentially
    aggregate up to way more than 52 weeks."
    """
    return _period_days(row) >= methodology.minimum_pay_period_days


def run_pay_period_method(
    rows: list[dict],
    *,
    tax_year: int,
    analysis_start_month: date,
    pack: OneZeroPack,
    fiscal_year_end_month: int = 12,
    fiscal_window: tuple[date, date] | None = None,
    recorder: TrailRecorder | None = None,
) -> OneZeroResult:
    """The partner's 7-step Pay Period Method. Returns an `OneZeroResult`."""
    if recorder is None:
        recorder = current_recorder()
    m = pack.methodology
    rows = apply_pay_code_policy(rows, pack)  # [L5] CALC-11
    months = _twelve_month_ends(analysis_start_month)
    rows = preprocess(
        rows,
        tax_year=tax_year,
        fiscal_year_end_month=fiscal_year_end_month,
        fiscal_window=fiscal_window,
        methodology=m,
        recorder=recorder,
    )

    # --- Step 1: Total Hours and Wages per employee ---
    # BA-12 asymmetry: the numerator keeps every row by default, including the
    # short periods that Step 3 excludes from the denominator. The money was
    # genuinely earned even when the pay period is an artefact.
    numerator_rows = (
        [r for r in rows if qualifies_as_pay_period(r, pack.methodology)]
        if pack.methodology.short_periods_excluded_from_numerator
        else rows
    )
    totals: dict[str, dict] = {}
    for r in numerator_rows:
        ee = r["Employee_ID"]
        slot = totals.setdefault(ee, {"Employee_ID": ee, "total_hours": 0.0, "total_wages": 0.0})
        slot["total_hours"] += _coerce_float(r["Hours_Worked"])
        slot["total_wages"] += _coerce_float(r["Gross_Wages"])
    for slot in totals.values():
        slot["total_hours"] = round(slot["total_hours"], 2)
        slot["total_wages"] = round(slot["total_wages"], 2)
    total_hours_and_wages = sorted(totals.values(), key=lambda x: x["Employee_ID"])
    if recorder:
        recorder.record(
            step="onezero.pp.step1_totals",
            inputs={"row_count": len(rows)},
            formula="sum(Hours_Worked) AND sum(Gross_Wages) GROUP BY Employee_ID",
            output={"employees": len(total_hours_and_wages)},
            citation="One Zero Pay Periods.docx Step 1",
        )

    # --- Step 2: Major pay periods per cycle ---
    is_major = _detect_major_pay_periods(rows)
    if recorder:
        major_count = sum(1 for v in is_major.values() if v)
        recorder.record(
            step="onezero.pp.step2_major_periods",
            inputs={"distinct_periods": len(is_major)},
            formula="bucket by frequency; period is major if employee_count >= median/2",
            output={"major_periods": major_count, "off_cycle_periods": len(is_major) - major_count},
            citation="One Zero Pay Periods.docx Step 2",
        )

    # --- Step 3: Weeks worked per employee (only major periods) ---
    # Determine each employee's primary cycle (most frequent freq across their
    # major periods) and collect the unique major (PPS, PPE) pairs they appeared
    # in. Collapsing to a set is what makes multiple pay-code lines within one
    # period count once - the step the partner found missing from their own 12 August
    # run: "I did not collapse the payroll... that's why I think my number was
    # wrong."
    ee_major_periods: dict[str, set[tuple[str, str]]] = defaultdict(set)
    ee_freq_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    short_period_rows = 0
    for r in rows:
        # BA-12: artefact periods are not real periods and add no weeks.
        if not qualifies_as_pay_period(r, m):
            short_period_rows += 1
            continue
        pps, ppe = r["Pay_Period_Start"], r["Pay_Period_End"]
        days = _period_days(r)
        freq = _infer_frequency(days)
        if m.exclude_off_cycle_periods and not is_major.get((pps, ppe, freq), False):
            continue
        ee_major_periods[r["Employee_ID"]].add((pps, ppe))
        ee_freq_counts[r["Employee_ID"]][freq] += 1

    weeks_worked: dict[str, dict] = {}
    over_53_weeks: list[dict] = []
    for ee, periods in ee_major_periods.items():
        primary_freq = max(ee_freq_counts[ee].items(), key=lambda kv: kv[1])[0] if ee_freq_counts[ee] else "weekly"
        if m.pay_period_denominator_mode == "frequency_code":
            # Legacy replay path only. See `_frequency_weeks_per_period`.
            weeks = len(periods) * _frequency_weeks_per_period(primary_freq)
        else:
            # BA-03: each period contributes its own measured span. The source
            # frequency code is lineage, never a multiplier.
            weeks = sum(
                ((_parse_iso(ppe) - _parse_iso(pps)).days + 1) / 7.0
                for pps, ppe in periods
            )
        # BA-06: the denominator keeps full precision; only the average rounds.
        weeks_worked[ee] = {
            "Employee_ID": ee,
            "weeks_worked": weeks,
            "pay_cycle": primary_freq,
            "major_period_count": len(periods),
        }        # BA-09: surface an implausible denominator, never silently cap it.
        if weeks > m.maximum_weeks_without_review:
            over_53_weeks.append({"Employee_ID": ee, "weeks_worked": weeks, "primary_freq": primary_freq})
    if recorder:
        formula = (
            "weeks_worked = COUNT(unique major periods) * weeks_per_period(primary_freq)"
            if m.pay_period_denominator_mode == "frequency_code"
            else "weeks_worked = SUM((PayPeriodEnd - PayPeriodStart + 1) / 7) over unique major periods"
        )
        recorder.record(
            step="onezero.pp.step3_weeks_worked",
            inputs={
                "employees_with_major_periods": len(weeks_worked),
                "minimum_pay_period_days": m.minimum_pay_period_days,
                "short_period_rows_excluded": short_period_rows,
            },
            formula=f"{formula}; periods spanning < {m.minimum_pay_period_days} days excluded",
            output={"employees": len(weeks_worked), "over_53_week_flags": len(over_53_weeks)},
            citation="One Zero Pay Periods.docx Step 3; BA-03, BA-12",
        )

    # --- Step 4: Averages ---
    averages: list[dict] = []
    for ee, totals_row in totals.items():
        ww = weeks_worked.get(ee)
        if not ww or ww["weeks_worked"] <= 0:
            continue
        avg_hours = _round_half_up(totals_row["total_hours"] / ww["weeks_worked"], m.average_decimals)
        avg_wages = _round_half_up(totals_row["total_wages"] / ww["weeks_worked"], m.average_decimals)
        averages.append({
            "Employee_ID": ee,
            "total_hours": totals_row["total_hours"],
            "total_wages": totals_row["total_wages"],
            "weeks_worked": round(ww["weeks_worked"], m.average_decimals),
            "avg_weekly_hours": avg_hours,
            "avg_weekly_wages": avg_wages,
        })
    averages.sort(key=lambda x: x["avg_weekly_wages"], reverse=True)
    if recorder:
        recorder.record(
            step="onezero.pp.step4_averages",
            inputs={"employees": len(averages)},
            formula="avg_weekly_hours = total_hours/weeks_worked; avg_weekly_wages = total_wages/weeks_worked",
            output={"employees": len(averages)},
            citation="One Zero Pay Periods.docx Step 4",
        )

    # --- Step 5: Eligibility filter ---
    eligible = _eligibility_filter(averages, pack)
    if recorder:
        recorder.record(
            step="onezero.pp.step5_eligible",
            inputs={"min_weekly_hours": pack.min_weekly_hours, "min_weekly_wages": pack.min_weekly_wages},
            formula=f"avg_weekly_hours >= {pack.min_weekly_hours} AND avg_weekly_wages >= {pack.min_weekly_wages}",
            output={"eligible_employees": len(eligible), "ineligible_employees": len(averages) - len(eligible)},
            citation=pack.citation,
        )
    eligible_ids = {e["Employee_ID"] for e in eligible}
    # [H2] CALC-03 — per-employee headcount weight (1.0 full-time, pt_weight part-time).
    eligible_weight = {e["Employee_ID"]: e.get("weight", 1.0) for e in eligible}

    # --- Step 6: One/Zero matrix (per eligible employee, per qualifying period, per unit) ---
    matrix: list[dict] = []
    for r in rows:
        if r["Employee_ID"] not in eligible_ids:
            continue
        if not qualifies_as_pay_period(r, m):
            continue
        pps, ppe = r["Pay_Period_Start"], r["Pay_Period_End"]
        days = _period_days(r)
        freq = _infer_frequency(days)
        if m.exclude_off_cycle_periods and not is_major.get((pps, ppe, freq), False):
            continue
        pps_d, ppe_d = _parse_iso(pps), _parse_iso(ppe)
        weight = eligible_weight.get(r["Employee_ID"], 1.0)
        row = {
            "Employee_ID": r["Employee_ID"],
            "Worksite_ID": r["Worksite_ID"],
            "Entity_FEIN": r.get("Entity_FEIN", ""),
            "Pay_Period_Start": pps,
            "Pay_Period_End": ppe,
            "Pay_Date": r["Pay_Date"],
            "weight": weight,
            "months": [],
        }
        # Find last PPE in this segment for Month-12 special rule
        last_ppe_for_ee_unit = ppe_d  # per-line, simplest interpretation
        for i, me in enumerate(months):
            base_target = _measuring_date_for_month(me, pack.measuring_date)  # [H3]
            target = _adjusted_target_for_month(base_target, last_ppe_for_ee_unit, is_month_12=(i == 11))
            covers = pps_d <= target <= ppe_d
            row["months"].append(weight if covers else 0)
        matrix.append(row)

    # No-employee-gets-more-than-one-1 sanity collapse: if the same EE appears
    # multiple times at the same unit, only one row should claim a given month.
    # Build a deterministic "first-1-wins" cleanup so the SUMMARY math is correct.
    matrix = _dedupe_one_per_month(matrix)
    if recorder:
        recorder.record(
            step="onezero.pp.step6_matrix",
            inputs={"eligible_employees": len(eligible_ids), "major_period_lines": len(matrix)},
            formula="for each (EE,Unit,major_period): 1 if PPS<=month_end<=PPE (Month-12 special rule applied)",
            output={"matrix_rows": len(matrix)},
            citation="One Zero Pay Periods.docx Step 6",
        )

    # --- Step 7: Summary by unit by month ---
    summary, avg_per_unit, annual_avg = _build_summary(matrix, months)
    if recorder:
        recorder.record(
            step="onezero.pp.step7_summary",
            inputs={"units": len(summary), "months": 12},
            formula="SUM(1s) per (Worksite_ID, month) -> 12-col table + 12-month average per unit",
            output={"unit_count": len(summary), "annual_average": annual_avg},
            citation="One Zero Pay Periods.docx Step 7",
        )

    flags: list[dict] = []
    for f in over_53_weeks:
        flags.append({"type": "over_53_weeks", "employee_id": f["Employee_ID"], "weeks": f["weeks_worked"]})

    return OneZeroResult(
        method="pay_period",
        tax_year=tax_year,
        analysis_start_month=analysis_start_month,
        months=months,
        total_hours_and_wages=total_hours_and_wages,
        eligible_employees=eligible,
        employee_unit_matrix=matrix,
        summary=summary,
        average_headcount=avg_per_unit,
        annual_average=annual_avg,
        flags=flags,
        all_averages=averages,
    )


def employee_derivation(
    rows: list[dict],
    *,
    employee_id: str,
    tax_year: int,
    analysis_start_month: date,
    pack: OneZeroPack,
    fiscal_year_end_month: int = 12,
) -> dict[str, Any] | None:
    """Full per-employee derivation chain for the drill-in (source → output).

    Runs the Pay Period Method and slices one employee's path out of it:
    source pay-period lines → totals → weeks worked → weekly averages → floor
    test (hours & wages) → weight (1 / pt_weight / 0) → per-month contribution
    → contribution to Average Headcount. This IS the engine output, sliced to
    one employee (no re-derivation), so the drill can never disagree with the
    headline. Returns None when the employee has no rows in scope.
    """
    res = run_pay_period_method(
        rows, tax_year=tax_year, analysis_start_month=analysis_start_month,
        pack=pack, fiscal_year_end_month=fiscal_year_end_month,
    )
    totals = next((t for t in res.total_hours_and_wages if t["Employee_ID"] == employee_id), None)
    avg = next((a for a in res.all_averages if a["Employee_ID"] == employee_id), None)
    elig = next((e for e in res.eligible_employees if e["Employee_ID"] == employee_id), None)
    if totals is None and avg is None:
        return None

    # Source pay-period lines for this employee (post pay-code policy).
    lines = [
        {
            "Worksite_ID": r.get("Worksite_ID"),
            "Entity_FEIN": r.get("Entity_FEIN"),
            "Pay_Period_Start": r.get("Pay_Period_Start"),
            "Pay_Period_End": r.get("Pay_Period_End"),
            "Pay_Date": r.get("Pay_Date"),
            "Hours_Worked": _coerce_float(r.get("Hours_Worked")),
            "Gross_Wages": _coerce_float(r.get("Gross_Wages")),
            "Pay_Code": r.get("Pay_Code", "Regular"),
        }
        for r in rows if r.get("Employee_ID") == employee_id
    ]
    lines.sort(key=lambda x: str(x["Pay_Period_End"]))

    weight = passed_hours = passed_wages = None
    if avg is not None:
        weight, passed_hours, passed_wages = _classify_eligibility(avg, pack)

    # Per-month contribution from the One/Zero matrix (which month each unit claims).
    month_labels = [m.isoformat() for m in res.months]
    matrix_rows = [m for m in res.employee_unit_matrix if m["Employee_ID"] == employee_id]
    monthly: list[dict] = []
    for i, ml in enumerate(month_labels):
        val: float = 0.0
        unit: str | None = None
        for mr in matrix_rows:
            v = mr["months"][i] if i < len(mr["months"]) else 0
            if v:
                val = v
                unit = mr["Worksite_ID"]
                break
        monthly.append({"month_end": ml, "counted": val, "worksite_id": unit})
    months_counted = sum(1 for m in monthly if m["counted"])

    return {
        "employee_id": employee_id,
        "tax_year": tax_year,
        "source_lines": lines,
        "source_line_count": len(lines),
        "totals": {
            "total_hours": totals["total_hours"] if totals else 0.0,
            "total_wages": totals["total_wages"] if totals else 0.0,
        },
        "weeks_worked": avg.get("weeks_worked") if avg else 0.0,
        "avg_weekly_hours": avg.get("avg_weekly_hours") if avg else None,
        "avg_weekly_wages": avg.get("avg_weekly_wages") if avg else None,
        "floor_test": {
            "min_weekly_hours": pack.min_weekly_hours,
            "min_weekly_wages": pack.min_weekly_wages,
            "wage_test_applies": pack.min_weekly_wages > 0,
            "passed_hours": passed_hours,
            "passed_wages": passed_wages,
            "weight": weight if weight is not None else 0.0,
        },
        "eligible": elig is not None,
        "months": monthly,
        "months_counted": months_counted,
        "headcount_contribution": round(sum(m["counted"] for m in monthly) / 12.0, 4),
        "citation": pack.citation,
    }


# ---------------------------------------------------------------------------
# Min Max Method (fallback for messy payroll)
# ---------------------------------------------------------------------------


def run_min_max_method(
    rows: list[dict],
    *,
    tax_year: int,
    analysis_start_month: date,
    pack: OneZeroPack,
    fiscal_year_end_month: int = 12,
    fiscal_window: tuple[date, date] | None = None,
    recorder: TrailRecorder | None = None,
) -> OneZeroResult:
    """The partner's 6-step Min Max Method. Returns an `OneZeroResult`.

    Same eligibility floors as Pay Period; weeks worked = (latest PPE - earliest
    PPS)/7 globally, and the One/Zero matrix uses one row per (Employee, Unit)
    where the range = [earliest PPS at that unit, latest PPE at that unit].
    """
    if recorder is None:
        recorder = current_recorder()
    m = pack.methodology
    rows = apply_pay_code_policy(rows, pack)  # [L5] CALC-11
    months = _twelve_month_ends(analysis_start_month)
    rows = preprocess(
        rows,
        tax_year=tax_year,
        fiscal_year_end_month=fiscal_year_end_month,
        fiscal_window=fiscal_window,
        methodology=m,
        recorder=recorder,
    )

    # --- Step 1: Totals per employee (same as Pay Period) ---
    # BA-12 asymmetry: by default every row contributes, including short
    # periods excluded from the Step 2 span. The partner, 2026-08-20: "I go back to
    # the stored payroll file where I aggregated all wages paid, all hours
    # worked, irrespective of good or bad pay periods."
    numerator_rows = (
        [r for r in rows if qualifies_as_pay_period(r, pack.methodology)]
        if pack.methodology.short_periods_excluded_from_numerator
        else rows
    )
    totals: dict[str, dict] = {}
    for r in numerator_rows:
        ee = r["Employee_ID"]
        slot = totals.setdefault(ee, {"Employee_ID": ee, "total_hours": 0.0, "total_wages": 0.0})
        slot["total_hours"] += _coerce_float(r["Hours_Worked"])
        slot["total_wages"] += _coerce_float(r["Gross_Wages"])
    for slot in totals.values():
        slot["total_hours"] = round(slot["total_hours"], 2)
        slot["total_wages"] = round(slot["total_wages"], 2)
    total_hours_and_wages = sorted(totals.values(), key=lambda x: x["Employee_ID"])
    if recorder:
        recorder.record(
            step="onezero.mm.step1_totals",
            inputs={"row_count": len(rows)},
            formula="sum(Hours_Worked), sum(Gross_Wages) GROUP BY Employee_ID",
            output={"employees": len(total_hours_and_wages)},
            citation="One Zero Min Max.docx Step 1",
        )

    # --- Step 2: Weeks worked = (latest PPE - earliest PPS) / 7 ---
    # BA-12: short periods define no span. A terminal cheque dated three months
    # after the last real period would otherwise stretch the denominator by a
    # quarter and sink the average. Their hours/wages stayed in Step 1.
    span_rows = [r for r in rows if qualifies_as_pay_period(r, m)]
    short_period_rows = len(rows) - len(span_rows)
    span: dict[str, dict] = {}
    for r in span_rows:
        ee = r["Employee_ID"]
        pps = _parse_iso(r["Pay_Period_Start"])
        ppe = _parse_iso(r["Pay_Period_End"])
        slot = span.setdefault(ee, {"first_start": pps, "last_end": ppe})
        if pps < slot["first_start"]:
            slot["first_start"] = pps
        if ppe > slot["last_end"]:
            slot["last_end"] = ppe
    weeks_worked: dict[str, dict] = {}
    for ee, sl in span.items():
        # BA-11: "count the number of days between the two and divide by 7" -
        # exclusive, so a full calendar year is 51.86 weeks and not 52.00. Full
        # precision is retained; only the resulting average rounds (BA-06).
        days = (sl["last_end"] - sl["first_start"]).days
        if m.min_max_span_mode == "inclusive_days":
            days += 1
        weeks = days / 7.0
        weeks_worked[ee] = {
            "Employee_ID": ee,
            "first_start": sl["first_start"],
            "last_end": sl["last_end"],
            "days": days,
            "weeks_worked": weeks,
        }
    if recorder:
        recorder.record(
            step="onezero.mm.step2_weeks",
            inputs={
                "employees": len(weeks_worked),
                "minimum_pay_period_days": m.minimum_pay_period_days,
                "short_period_rows_excluded": short_period_rows,
            },
            formula=(
                "weeks_worked = (latest PayPeriodEnd - earliest PayPeriodStart) / 7"
                f" over periods spanning >= {m.minimum_pay_period_days} days"
                f" ({m.min_max_span_mode})"
            ),
            output={"employees": len(weeks_worked)},
            citation="One Zero Min Max.docx Step 2; BA-11, BA-12",
        )

    # --- Step 3: Averages ---
    averages: list[dict] = []
    for ee, t in totals.items():
        ww = weeks_worked.get(ee)
        if not ww or ww["weeks_worked"] <= 0:
            continue
        averages.append({
            "Employee_ID": ee,
            "total_hours": t["total_hours"],
            "total_wages": t["total_wages"],
            "first_start": ww["first_start"].isoformat(),
            "last_end": ww["last_end"].isoformat(),
            "days": ww["days"],
            "weeks_worked": round(ww["weeks_worked"], m.average_decimals),
            "avg_weekly_hours": _round_half_up(t["total_hours"] / ww["weeks_worked"], m.average_decimals),
            "avg_weekly_wages": _round_half_up(t["total_wages"] / ww["weeks_worked"], m.average_decimals),
        })
    averages.sort(key=lambda x: x["avg_weekly_wages"], reverse=True)
    if recorder:
        recorder.record(
            step="onezero.mm.step3_averages",
            inputs={"employees": len(averages)},
            formula="avg_weekly_* = total_*/weeks_worked",
            output={"employees": len(averages)},
            citation="One Zero Min Max.docx Step 3",
        )

    # --- Step 4: Eligibility ---
    eligible = _eligibility_filter(averages, pack)
    if recorder:
        recorder.record(
            step="onezero.mm.step4_eligible",
            inputs={"min_weekly_hours": pack.min_weekly_hours, "min_weekly_wages": pack.min_weekly_wages},
            formula=f"avg_weekly_hours >= {pack.min_weekly_hours} AND avg_weekly_wages >= {pack.min_weekly_wages}",
            output={"eligible_employees": len(eligible), "ineligible_employees": len(averages) - len(eligible)},
            citation=pack.citation,
        )
    eligible_ids = {e["Employee_ID"] for e in eligible}
    # [H2] CALC-03 — per-employee headcount weight (1.0 full-time, pt_weight part-time).
    eligible_weight = {e["Employee_ID"]: e.get("weight", 1.0) for e in eligible}

    # --- Step 5: One/Zero matrix - one line per (Employee, Unit) ---
    # For each eligible EE-Unit combo, take earliest PPS at unit and latest PPE at unit.
    ee_unit_span: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r["Employee_ID"] not in eligible_ids:
            continue
        key = (r["Employee_ID"], r["Worksite_ID"])
        pps = _parse_iso(r["Pay_Period_Start"])
        ppe = _parse_iso(r["Pay_Period_End"])
        slot = ee_unit_span.setdefault(key, {"first_pps": pps, "last_ppe": ppe, "Entity_FEIN": r.get("Entity_FEIN", "")})
        if pps < slot["first_pps"]:
            slot["first_pps"] = pps
        if ppe > slot["last_ppe"]:
            slot["last_ppe"] = ppe

    matrix: list[dict] = []
    for (ee, unit), sl in ee_unit_span.items():
        weight = eligible_weight.get(ee, 1.0)
        row = {
            "Employee_ID": ee,
            "Worksite_ID": unit,
            "Entity_FEIN": sl.get("Entity_FEIN", ""),
            "first_pps": sl["first_pps"].isoformat(),
            "last_ppe": sl["last_ppe"].isoformat(),
            "weight": weight,
            "months": [],
        }
        for i, me in enumerate(months):
            base_target = _measuring_date_for_month(me, pack.measuring_date)  # [H3]
            target = _adjusted_target_for_month(base_target, sl["last_ppe"], is_month_12=(i == 11))
            covers = sl["first_pps"] <= target <= sl["last_ppe"]
            row["months"].append(weight if covers else 0)
        matrix.append(row)
    matrix.sort(key=lambda r: (r["Employee_ID"], r["Worksite_ID"]))

    # Flag duplicates (same EE, more than one 1 in any month across units).
    dup_flags: list[dict] = []
    by_ee_month: dict[tuple[str, int], int] = defaultdict(int)
    for row in matrix:
        for i, v in enumerate(row["months"]):
            by_ee_month[(row["Employee_ID"], i)] += v
    for (ee, i), c in by_ee_month.items():
        if c > 1:
            dup_flags.append({"type": "multi_unit_double_count", "employee_id": ee, "month_index": i, "count": c})

    if recorder:
        recorder.record(
            step="onezero.mm.step5_matrix",
            inputs={"eligible_employees": len(eligible_ids)},
            formula="for each (EE,Unit): 1 if first_pps<=month_end<=last_ppe (Month-12 special rule)",
            output={"matrix_rows": len(matrix), "double_count_flags": len(dup_flags)},
            citation="One Zero Min Max.docx Step 5",
        )

    # Apply tie-breaker so no employee counts twice in the same month (most
    # recent unit wins) before building the summary. `dup_flags` above records
    # every candidate, so the disposition is evidenced rather than silent.
    dedup_matrix = _dedupe_one_per_month(matrix)

    # --- Step 6: Summary ---
    summary, avg_per_unit, annual_avg = _build_summary(dedup_matrix, months)
    if recorder:
        recorder.record(
            step="onezero.mm.step6_summary",
            inputs={"units": len(summary), "months": 12},
            formula="SUM(1s) per (Worksite_ID, month) -> 12-col table + 12-month average per unit",
            output={"unit_count": len(summary), "annual_average": annual_avg},
            citation="One Zero Min Max.docx Step 6",
        )

    flags = dup_flags
    return OneZeroResult(
        method="min_max",
        tax_year=tax_year,
        analysis_start_month=analysis_start_month,
        months=months,
        total_hours_and_wages=total_hours_and_wages,
        eligible_employees=eligible,
        employee_unit_matrix=dedup_matrix,
        summary=summary,
        average_headcount=avg_per_unit,
        annual_average=annual_avg,
        flags=flags,
        # Every employee's average, ineligible included. Min Max computed these
        # in Step 3 and dropped them on the floor, so the drill-in and the
        # threshold-proximity read (`tools/proximity.py`) saw an empty list from
        # this method while Pay Period returned a full one. Nothing raised —
        # callers just got zero rows and an HTTP 200.
        all_averages=averages,
    )


# ---------------------------------------------------------------------------
# Shared post-processing
# ---------------------------------------------------------------------------


def _dedupe_one_per_month(matrix: list[dict]) -> list[dict]:
    """Enforce the "no employee may have more than one 1 in any month" rule.

    If the same employee is at multiple units in the same month, keep the 1
    on the unit with the highest cumulative hours for that employee (proxy
    for primary unit). For the prototype's deterministic synthetic data this
    is simply: the unit whose row appears LAST in the input order (i.e., the
    most recent unit chronologically) wins.
    """
    # Build EE -> [(idx, row)] map
    out_matrix = [{**r, "months": list(r["months"])} for r in matrix]
    by_ee: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(out_matrix):
        by_ee[r["Employee_ID"]].append(i)
    for ee, idxs in by_ee.items():
        if len(idxs) <= 1:
            continue
        # For each month col, if >1 row carries a non-zero value, keep the LAST
        # one (most recent unit). Values may be fractional (0.5 part-time) so we
        # test "> 0" rather than "== 1". [H2]
        for m in range(12):
            with_val = [i for i in idxs if out_matrix[i]["months"][m] > 0]
            if len(with_val) > 1:
                keeper = with_val[-1]
                for i in with_val:
                    if i != keeper:
                        out_matrix[i]["months"][m] = 0
    return out_matrix


def _build_summary(matrix: list[dict], months: list[date]) -> tuple[list[dict], dict[str, float], float]:
    """Build the per-unit-per-month summary, the per-unit 12-month average,
    and the overall annual average across all units.

    Month totals and averages are kept to 2 decimals so part-time 0.5 weights
    [H2] survive into the Average Headcount instead of being rounded away.
    """
    by_unit: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    for row in matrix:
        for m in range(12):
            by_unit[row["Worksite_ID"]][m] += row["months"][m]
    summary: list[dict] = []
    avg_per_unit: dict[str, float] = {}
    for unit in sorted(by_unit.keys()):
        cols = [round(c, 2) for c in by_unit[unit]]
        total = round(sum(cols), 2)
        avg = round(total / 12.0, 2)
        summary.append({
            "Worksite_ID": unit,
            "month_totals": cols,
            "total": total,
            "average_headcount": avg,
        })
        avg_per_unit[unit] = avg
    annual_avg = round(sum(avg_per_unit.values()), 2) if avg_per_unit else 0.0
    return summary, avg_per_unit, annual_avg

# ---------------------------------------------------------------------------
# Extracted, re-exported
# ---------------------------------------------------------------------------
# Matrix roll-ups, method reconciliation and the performance dashboard moved to
# sibling modules. None of them is part of computing a statutory figure - they
# aggregate, compare and project over results the engine has already produced -
# and keeping them here made this file about four things instead of one.
#
# Re-exported so existing imports keep working. New code should import from the
# module that owns the concern.
from .performance import run_performance_dashboard  # noqa: E402,F401
from .reconciliation import ReconciliationReport, reconcile_methods  # noqa: E402,F401
from .rollups import rollup_matrix_by_field, rollup_matrix_by_two_fields  # noqa: E402,F401
