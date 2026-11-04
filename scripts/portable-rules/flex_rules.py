"""
Flex / Tax Credit Copilot — deterministic business rules, portable.

WHAT THIS IS
    The rules that turn raw partner payroll into a Georgia JTC headcount,
    extracted from the certified engine as pure functions with no dependencies
    beyond the Python standard library. Drop this file into a Fabric notebook,
    a Spark job, or a plain script and it runs.

WHY IT EXISTS
    So a pipeline implementation can be checked against the reference one rule
    at a time, rather than only at the final number. Every function here has a
    single job, names the rule it implements, and cites the source document.

WHAT IT IS NOT
    Not the production engine. The engine carries provenance recording, rule
    packs resolved per tax year, agent surfaces and a soft-delete audit trail;
    none of that is here. The arithmetic is identical — this file is generated
    from the same rules and verified against the same certified figures.

PRECISION
    Decimal throughout, never float. Money and hours divided by weeks and then
    rounded half-up to two decimals, and the ROUNDED value is what the
    thresholds test. float would give you 34.999999 where the engine gives
    35.00, and that is the difference between an eligible employee and an
    ineligible one.

RULE INDEX
    BA-01  fiscal window is per-client configuration       fiscal_window()
    BA-02  select on paycheck date only                    select_rows()
    BA-04  collapse exact duplicate payroll facts          collapse_duplicates()
    BA-03  collapse pay-code lines to one period           period_weeks()
    BA-05  keep negative and zero-hour corrections         employee_totals()
    BA-12  exclude pay periods under 7 days                is_real_pay_period()
    BA-11  Min-Max weeks, exclusive day count              min_max_weeks()
    BA-06  eligibility on rounded weekly averages          test_eligibility()
    OZ-01  twelve month-end targets                        month_end_targets()
    OZ-04  Month 12 exception                              measuring_date()
    OZ-02  a month scores when the span covers the target  onezero_row()
    OZ-07  average headcount = total / 12                  unit_summary()

Verified against the certified reference run:
    10,236 employees · 539 Min-Max eligible · 656 Pay Period eligible · TY2023

Source of truth: docs/data/CALCULATION-RULES-V7.md in the tax-credit-copilot
repo. Where this file and that document disagree, the document is right.

Generated 2026-09-04 from commit d1beefe.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "MIN_PAY_PERIOD_DAYS",
    "MONTHS_IN_YEAR",
    "GA_JTC_TY2023",
    "to_decimal",
    "round_half_up",
    "fiscal_window",
    "select_rows",
    "collapse_duplicates",
    "is_real_pay_period",
    "employee_totals",
    "min_max_weeks",
    "period_weeks",
    "test_eligibility",
    "month_end_targets",
    "measuring_date",
    "onezero_row",
    "unit_summary",
    "unreachable_months",
    "year_is_complete",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: BA-12. A pay period shorter than this is not a real unit of elapsed time.
MIN_PAY_PERIOD_DAYS = 7

#: The One/Zero denominator. Always twelve, including months that scored zero.
MONTHS_IN_YEAR = 12

#: BA-06. Georgia JTC floors for Tax Year 2023. The wage floor is the DOL 2022
#: average weekly wage for Glascock County: $33,072 / 52 = $636. Confirmed by
#: the partner on the 6 August 2026 call.
#:
#: These are per tax year. Do not reuse them for another year without the
#: matching DCA table.
GA_JTC_TY2023 = {
    "program_code": "GA_JTC",
    "tax_year": 2023,
    "min_weekly_hours": Decimal("35"),
    "min_weekly_wages": Decimal("636"),
    "citation": "O.C.G.A. 48-7-40",
}


# ---------------------------------------------------------------------------
# Precision helpers
# ---------------------------------------------------------------------------


def to_decimal(value: Any) -> Decimal:
    """Coerce to Decimal without going through float.

    `Decimal(str(x))` rather than `Decimal(x)` on purpose: a float that reads
    2061.19 is really 2061.18999999999996362, and Decimal(float) carries that
    error forward. Going via str takes the value as written.

    Empty and None become zero — a missing wage is not a wage of unknown size,
    it is a row that contributes nothing. NULL versus 0 in the SOURCE is a
    different question and is open with the partner (Q2 in the schema mapping).
    """
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_half_up(value: Decimal, places: int = 2) -> Decimal:
    """Round half away from zero, which is what a person means by rounding.

    Python's built-in round() is banker's rounding: round(0.5) == 0. Georgia
    does not file banker's rounding.
    """
    exp = Decimal(1).scaleb(-places)
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def _as_date(value: Any) -> date:
    """Accept a date, a datetime, or an ISO-ish string."""
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    return date.fromisoformat(text)


# ---------------------------------------------------------------------------
# Stage 1 — selecting the fiscal year
# ---------------------------------------------------------------------------


def fiscal_window(client_config: Mapping[str, Any]) -> tuple[date, date]:
    """BA-01. The analysis window comes from configuration, never from payroll.

    Fiscal years cannot be inferred. Public filers take theirs from the 10-K,
    many private flow-throughs are calendar year, and some are rule-based —
    "the Saturday nearest 31 July". The reference client runs 2023-07-28 to
    2024-08-02, a 53-week calendar that no month-end rule can express.

    In the partner's schema this is `Entity.FiscalYearRulesId` ->
    `EntityFiscalYearRules`. That table has not been supplied yet and is the
    highest-priority outstanding item.

    >>> fiscal_window({"fiscal_begin": "2023-07-28", "fiscal_end": "2024-08-02"})
    (datetime.date(2023, 7, 28), datetime.date(2024, 8, 2))
    """
    return _as_date(client_config["fiscal_begin"]), _as_date(client_config["fiscal_end"])


def select_rows(
    rows: Iterable[Mapping[str, Any]],
    fiscal_begin: date,
    fiscal_end: date,
    *,
    pay_date_field: str = "pay_date",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """BA-02. Include a row when its PAYCHECK DATE falls in the window.

    Nothing else is tested. A pay period ending after the fiscal year end is
    still included when the cheque was issued inside the window, and a period
    that began before the window opens is included on the same basis.

        The partner, 20 Aug 2026: "You wouldn't take a pay period, even if
        it started in the current year, but it was paid in the next year. And
        conversely, you can pick up a pay period that was started last year,
        but paid this year."

    This is cash-basis selection and it is the single most common thing to get
    wrong, because the intuitive filter is on pay period end.

    Returns (selected_rows, counts). The counts are for reconciliation — on the
    reference dataset this selection reproduces the partner's control totals exactly:
    384,418 records, 4,950,777.43 hours, $82,533,629.87 wages, 10,236 employees.
    """
    selected: list[dict[str, Any]] = []
    counts: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        counts["input"] += 1
        pay_date = _as_date(row[pay_date_field])
        if pay_date < fiscal_begin:
            counts["excluded_pay_date_before_window"] += 1
        elif pay_date > fiscal_end:
            counts["excluded_pay_date_after_window"] += 1
        else:
            selected.append(dict(row))
            counts["included"] += 1

    return selected, dict(counts)


# ---------------------------------------------------------------------------
# Stage 2 — normalising the payroll
# ---------------------------------------------------------------------------


def collapse_duplicates(
    rows: Iterable[Mapping[str, Any]],
    *,
    employee_field: str = "employee_id",
    unit_field: str = "unit_id",
    fein_field: str = "fein",
    start_field: str = "pay_period_start",
    end_field: str = "pay_period_end",
    pay_date_field: str = "pay_date",
    frequency_field: str = "pay_frequency",
    hours_field: str = "hours",
    wages_field: str = "wages",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """BA-04 and BA-03. Collapse multiple source lines into one period row.

    Group on employee, unit, FEIN, period start, period end, paycheck date and
    pay frequency; sum the signed hours and wages. Modern payroll extracts
    carry several rows per pay period — regular, overtime, bonus — and each
    must become ONE period for denominator purposes.

    This is the step the partner identified as missing from their own Pay Period run:

        "I could have one, two, 10 different lines for any one pay period... I
        did not collapse the payroll. So I was counting up too many ones or too
        many twos. That's why I think my number was wrong."

    If your pipeline counts pay periods without collapsing first, the
    denominator inflates and every average comes out low.

    `source_rows` on each output row keeps the lineage — how many source lines
    folded into it.
    """
    grouped: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row[employee_field]),
            str(row.get(unit_field, "")),
            str(row.get(fein_field, "")),
            _as_date(row[start_field]),
            _as_date(row[end_field]),
            _as_date(row[pay_date_field]),
            str(row.get(frequency_field, "")),
        )
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {
                "employee_id": key[0],
                "unit_id": key[1],
                "fein": key[2],
                "pay_period_start": key[3],
                "pay_period_end": key[4],
                "pay_date": key[5],
                "pay_frequency": key[6],
                "hours": to_decimal(row.get(hours_field)),
                "wages": to_decimal(row.get(wages_field)),
                "source_rows": 1,
            }
        else:
            existing["hours"] += to_decimal(row.get(hours_field))
            existing["wages"] += to_decimal(row.get(wages_field))
            existing["source_rows"] += 1

    collapsed = list(grouped.values())
    input_count = sum(r["source_rows"] for r in collapsed)
    return collapsed, {
        "input_rows": input_count,
        "collapsed_rows": len(collapsed),
        "duplicate_rows_collapsed": input_count - len(collapsed),
        "multi_line_groups": sum(1 for r in collapsed if r["source_rows"] > 1),
    }


# ---------------------------------------------------------------------------
# Stage 3 — removing periods that are not real
# ---------------------------------------------------------------------------


def is_real_pay_period(
    row: Mapping[str, Any],
    minimum_days: int = MIN_PAY_PERIOD_DAYS,
) -> bool:
    """BA-12. A pay period shorter than seven days is not a real pay period.

        The partner, 20 Aug 2026: "You get a lot of these garbagey pay periods that
        come through — one day pay periods, two day pay periods, and they all
        have a one. So if you include those, you're going to potentially
        aggregate up to way more than 52 weeks in a year."

    THE ASYMMETRY IS DELIBERATE and it is the thing most likely to differ
    between two implementations:

        excluded from  ->  the denominator, the Min-Max span, the One/Zero
                           segment span
        retained in    ->  the numerator (hours and wages)

    A one-day period is real money the employee earned, so it belongs in the
    numerator; it is not a real unit of elapsed time, so counting it in the
    denominator distorts the average. The partner's worked example: an employee with a
    four-day period and 81 hours grossed up to 142 hours per week — "they only
    really worked 81 hours, but it grossed up to 142 hours."

    On the reference dataset this excludes 1,705 rows carrying 7,726.49 hours
    and $1,859,776.29 in wages, touching 998 employees, of whom 156 are left
    with no qualifying pay period at all.

    Span is INCLUSIVE here — a Monday-to-Sunday period is 7 days and qualifies.
    Note that BA-11 measures the Min-Max span exclusively; the two differ on
    purpose and it is not a bug.

    Pass minimum_days=0 to disable, which is how earlier assumption sets replay.
    """
    if minimum_days <= 0:
        return True
    start = _as_date(row["pay_period_start"])
    end = _as_date(row["pay_period_end"])
    return (end - start).days + 1 >= minimum_days


def short_period_exclusions(
    rows: Iterable[Mapping[str, Any]],
    minimum_days: int = MIN_PAY_PERIOD_DAYS,
) -> list[dict[str, Any]]:
    """Every row BA-12 removes, with the reason, for review.

    Exclusions are a SOFT DELETE, never a silent drop.

        The partner: "Maybe you capture the ineligibles and then give the user the
        ability to review the ineligibles and say, well, wait a minute, that
        one should be eligible. Let's put it back over there."

    Your pipeline should write these somewhere a reviewer can see them.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if is_real_pay_period(row, minimum_days):
            continue
        start = _as_date(row["pay_period_start"])
        end = _as_date(row["pay_period_end"])
        out.append({
            "employee_id": row.get("employee_id"),
            "unit_id": row.get("unit_id"),
            "pay_period_start": start,
            "pay_period_end": end,
            "period_days": (end - start).days + 1,
            "hours": to_decimal(row.get("hours")),
            "wages": to_decimal(row.get("wages")),
            "rule": "BA-12",
            "reason": f"pay period under {minimum_days} days",
        })
    return out


# ---------------------------------------------------------------------------
# Stage 4 — the numerator and the two denominators
# ---------------------------------------------------------------------------


def employee_totals(
    rows: Iterable[Mapping[str, Any]],
    *,
    minimum_days: int = MIN_PAY_PERIOD_DAYS,
    short_periods_excluded_from_numerator: bool = False,
) -> dict[str, dict[str, Decimal]]:
    """BA-05. Sum each employee's hours and wages — the shared numerator.

    Both methods divide these same totals by their own denominator. Totals are
    customer-wide; unit and FEIN are ignored until One/Zero allocation, because
    both source documents say simply "add up the total hours and total wages
    for each employee".

    BA-05: signed corrections are PRESERVED. Negative hours and negative wages
    are real payroll facts and stay in. Wage rows carrying no hours stay too.
    Dropping negatives is a common pipeline reflex and it will silently inflate
    every total.

    `short_periods_excluded_from_numerator` defaults False per BA-12 — short
    periods stay in the numerator. The certified run uses False. It is exposed
    because the partner's own output contradicts their own description on this point, and
    the flag lets you test both readings.
    """
    totals: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        if short_periods_excluded_from_numerator and not is_real_pay_period(row, minimum_days):
            continue
        emp = str(row["employee_id"])
        bucket = totals.setdefault(emp, {"total_hours": Decimal("0"), "total_wages": Decimal("0")})
        bucket["total_hours"] += to_decimal(row.get("hours"))
        bucket["total_wages"] += to_decimal(row.get("wages"))
    return totals


def min_max_weeks(
    employee_rows: Sequence[Mapping[str, Any]],
    *,
    minimum_days: int = MIN_PAY_PERIOD_DAYS,
    exclude_zero_hour_rows: bool = False,
    inclusive_days: bool = False,
) -> tuple[Decimal, dict[str, Any]]:
    """BA-11. Min-Max weeks = (last PPE - first PPS) / 7, EXCLUSIVE day count.

        One Zero Min Max.docx Step 2: "Using the earliest PayPeriodStart date
        for each employee and the latest PayPeriodEnd date for each employee,
        count the number of days between the two and divide by 7."

    "Days between" is read literally as exclusive, so a full-year weekly
    employee lands on 51.86 weeks rather than 52.00. That reading was confirmed
    empirically — the partner's reported weeks reproduce exactly for eight of the nine
    employees the partner detailed on 12 August 2026.

    If your pipeline gives 52.00 where this gives 51.86, you have added the
    inclusive day. It is a ~0.3% difference in the denominator, which is enough
    to move a borderline employee across the wage floor.

    Short periods are dropped BEFORE the span is measured (BA-12), which is
    what moved several of the partner's employees' Min and Max dates relative to ours.

    Returns (weeks, detail). Zero weeks means no qualifying period; the
    employee is reported, never silently dropped.
    """
    work = [r for r in employee_rows if is_real_pay_period(r, minimum_days)]
    if exclude_zero_hour_rows:
        work = [r for r in work if to_decimal(r.get("hours")) > 0]

    if not work:
        return Decimal("0"), {"reason": "no_qualifying_pay_period"}

    first_start = min(_as_date(r["pay_period_start"]) for r in work)
    last_end = max(_as_date(r["pay_period_end"]) for r in work)
    span_days = (last_end - first_start).days + (1 if inclusive_days else 0)

    return Decimal(span_days) / Decimal("7"), {
        "first_start": first_start,
        "last_end": last_end,
        "span_days": span_days,
        "span_mode": "inclusive_days" if inclusive_days else "exclusive_days",
    }


def period_weeks(
    employee_rows: Sequence[Mapping[str, Any]],
    *,
    minimum_days: int = MIN_PAY_PERIOD_DAYS,
) -> tuple[Decimal, dict[str, Any]]:
    """BA-03. Pay Period weeks = sum over included periods of (end - start + 1) / 7.

    INCLUSIVE here, unlike BA-11. Each period contributes its own measured span.

    The source `PayFrequency` code is retained as lineage but is NOT used as a
    week multiplier. `FlexSchema.txt` shows it is `Payroll.PayFrequencyId`, a
    surrogate foreign key into a `dbo.PayFrequency` lookup that has not been
    supplied — so any meaning read into the code is a guess. Measured against
    actual spans in the reference dataset:

        code 1   374,535 rows   7 days (372,285 of them)
        code 2     7,153 rows   15 days, then 14
        code 4     2,745 rows   16 days — every single one

    Reading 4 as "every four weeks" produced 447 eligible against the partner's 659.
    The measured span is authoritative because it is observed rather than
    asserted, and it is what the partner's own output does.

        The partner: "fours are rarities... usually fours are miscoded twos."

    Periods are DEDUPLICATED on (start, end) — an employee's multiple source
    lines for one period contribute one period's worth of weeks. If you have
    not collapsed (BA-04) this will still protect you, but collapse anyway.
    """
    seen: set[tuple[date, date]] = set()
    weeks = Decimal("0")
    for row in employee_rows:
        if not is_real_pay_period(row, minimum_days):
            continue
        start = _as_date(row["pay_period_start"])
        end = _as_date(row["pay_period_end"])
        if (start, end) in seen:
            continue
        seen.add((start, end))
        weeks += Decimal((end - start).days + 1) / Decimal("7")

    return weeks, {"periods_counted": len(seen)}


# ---------------------------------------------------------------------------
# Stage 5 — the eligibility test
# ---------------------------------------------------------------------------


def test_eligibility(
    totals: Mapping[str, Decimal],
    weeks: Decimal,
    *,
    min_weekly_hours: Decimal = GA_JTC_TY2023["min_weekly_hours"],
    min_weekly_wages: Decimal = GA_JTC_TY2023["min_weekly_wages"],
    decimals: int = 2,
) -> dict[str, Any]:
    """BA-06. Qualify on the ROUNDED average weekly hours and wages.

    Round to two decimals half-up FIRST, then compare. The rounded value is
    what the threshold tests, which admits an employee whose unrounded average
    is 34.9998 hours. The partner endorsed that explicitly:

        "When they're working 34.99 hours, why not include them? I'm a big fan
        of giving the auditors things to throw out."

    Comparing the unrounded value instead will drop employees the reference run
    keeps. This is the second most common source of a small eligibility
    discrepancy, after the BA-11 day count.

    TY2023 Georgia floors are 35 hours and $636/week. The wage floor is per tax
    year from the DCA table — do not carry it to another year.
    """
    if weeks <= 0:
        avg_hours = avg_wages = Decimal("0")
    else:
        avg_hours = totals["total_hours"] / weeks
        avg_wages = totals["total_wages"] / weeks

    rounded_hours = round_half_up(avg_hours, decimals)
    rounded_wages = round_half_up(avg_wages, decimals)

    passed_hours = weeks > 0 and rounded_hours >= min_weekly_hours
    passed_wages = weeks > 0 and rounded_wages >= min_weekly_wages

    return {
        "total_hours": totals["total_hours"],
        "total_wages": totals["total_wages"],
        "denominator_weeks": weeks,
        "avg_weekly_hours": avg_hours,
        "avg_weekly_wages": avg_wages,
        "rounded_avg_weekly_hours": rounded_hours,
        "rounded_avg_weekly_wages": rounded_wages,
        "passed_hours": passed_hours,
        "passed_wages": passed_wages,
        "eligible": passed_hours and passed_wages,
    }


# ---------------------------------------------------------------------------
# Stage 6 — the One/Zero headcount matrix
# ---------------------------------------------------------------------------


def month_end_targets(first_month_end: date, count: int = MONTHS_IN_YEAR) -> list[date]:
    """OZ-01. Twelve month-end dates, pinned explicitly.

    For the reference dataset: August 2023 through July 2024. The window is
    CONFIGURED rather than derived from the fiscal year start, because the v7
    window opens on 28 July and deriving month ends from it would silently
    shift the entire matrix by a month.

    >>> month_end_targets(date(2023, 8, 31), 3)
    [datetime.date(2023, 8, 31), datetime.date(2023, 9, 30), datetime.date(2023, 10, 31)]
    """
    out: list[date] = []
    year, month = first_month_end.year, first_month_end.month
    for _ in range(count):
        if month == 12:
            nxt = date(year + 1, 1, 1)
        else:
            nxt = date(year, month + 1, 1)
        out.append(nxt - timedelta(days=1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def measuring_date(
    month_end: date,
    last_ppe: date,
    *,
    is_final_month: bool = False,
    day_threshold: int = 15,
) -> date:
    """OZ-04. Month 12 exception — the target moves to the last period end.

    If the employee's last pay period end falls in the final month on a day
    AFTER the 15th, that date becomes the target instead of month end.

    LOAD-BEARING. On a calendar-year client nothing spans 31 December, so
    without this rule Month 12 reads zero for everyone.

    OPEN ISSUE — questions 23-25 for the partner. This is a cliff. On the Cascade
    fixture a final period ending 12-15 scores Month 12 as 0, while 12-16
    scores ~25. A one-day difference in the pay calendar moves a location's
    annual average by roughly 8%, and therefore the credit. Two of six years
    are affected on that client. Do not treat this rule as settled.
    """
    if not is_final_month:
        return month_end
    if last_ppe.year == month_end.year and last_ppe.month == month_end.month:
        if last_ppe.day > day_threshold:
            return last_ppe
    return month_end


def onezero_row(
    first_pps: date,
    last_ppe: date,
    months: Sequence[date],
    *,
    weight: Decimal = Decimal("1"),
) -> list[Decimal]:
    """OZ-02 and OZ-03. A month scores when the segment covers the target.

    The span's pay period start must be on or before the measuring date and its
    pay period end on or after it. Min-Max segments span the employee's whole
    time at a unit; Pay Period segments are per period.

    `weight` is 1.0 for full-time and the pack's part-time weight otherwise
    (CALC-03). Georgia does not band part-time, so it is 1.0 there.

    Returns twelve Decimals. Store them as twelve COLUMNS, not an array — BI
    reads a column as a filterable dimension and an array as an opaque blob.
    """
    cells: list[Decimal] = []
    final_index = len(months) - 1
    for i, month_end in enumerate(months):
        target = measuring_date(month_end, last_ppe, is_final_month=(i == final_index))
        covers = first_pps <= target <= last_ppe
        cells.append(weight if covers else Decimal("0"))
    return cells


def unit_summary(matrix_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """OZ-07. Average headcount = the twelve monthly totals divided by twelve.

    THE DIVISOR IS ALWAYS TWELVE, including months that scored zero. That
    matches the partner's own summary output. It is question 24 on the outstanding
    list — the partner's Min-Max summary reports 0 for Month 4 across all 101 units while
    the average column still divides by 12 — but until the partner says otherwise, we
    divide by 12 to match them.

    Do not "improve" this to divide by months-with-data. It will look more
    correct and it will not tie out.

    Each input row needs `unit_id` and `months` (a sequence of twelve values).
    """
    by_unit: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal("0")] * MONTHS_IN_YEAR)
    for row in matrix_rows:
        unit = str(row["unit_id"])
        for i, value in enumerate(row["months"][:MONTHS_IN_YEAR]):
            by_unit[unit][i] += to_decimal(value)

    out: list[dict[str, Any]] = []
    for unit in sorted(by_unit):
        cols = [round_half_up(v, 2) for v in by_unit[unit]]
        total = round_half_up(sum(cols), 2)
        out.append({
            "unit_id": unit,
            "month_totals": cols,
            "total": total,
            "average_headcount": round_half_up(total / Decimal(MONTHS_IN_YEAR), 2),
            "months_with_headcount": sum(1 for v in cols if v > 0),
        })
    return out


# ---------------------------------------------------------------------------
# Year completeness — changed 2 September 2026
# ---------------------------------------------------------------------------


def unreachable_months(
    rows: Iterable[Mapping[str, Any]],
    months: Sequence[date],
) -> list[int]:
    """Month positions that NO pay period spans.

    A month scores only when some pay period covers its measuring date. For a
    calendar-year client no period spans 31 December, so month 12 is
    structurally unreachable and reads zero for reasons that have nothing to do
    with the location emptying out.

    Surface these. A hatched cell in a grid is honest; a zero is not.
    """
    spans = [
        (_as_date(r["pay_period_start"]), _as_date(r["pay_period_end"]))
        for r in rows
    ]
    out: list[int] = []
    for i, month_end in enumerate(months):
        if not any(start <= month_end <= end for start, end in spans):
            out.append(i)
    return out


def year_is_complete(
    months_reached: int,
    months_reachable: int,
) -> bool:
    """A year is complete when it fills every REACHABLE month, not all twelve.

    CHANGED 2 SEPTEMBER 2026, from the partner's feedback. This is the most leveraged
    input in the model and the change moved a published number.

    A calendar-year client has no December measuring date, so ELEVEN months is
    that client's complete year. Judging against twelve rejected it as a base
    year and pushed the base a year later. On the reference portfolio:

        Cascade base year   TY2021  ->  TY2020
        Portfolio claim     229,285 ->  607,110
        Certified figures   unmoved

    THE DIVISOR STAYS 12 (see unit_summary). Only the completeness test
    changed. Those are different questions and conflating them will move every
    average.
    """
    if months_reachable <= 0:
        return False
    return months_reached >= months_reachable


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def _self_check() -> list[tuple[str, bool, str]]:
    """Assertions a correct implementation must satisfy. Run this file to see them."""
    results: list[tuple[str, bool, str]] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        results.append((name, actual == expected, f"got {actual!r}, expected {expected!r}"))

    # BA-02 — selection is on pay date, not period end.
    rows = [
        {"employee_id": "A", "pay_date": "2023-08-04", "pay_period_start": "2023-07-24",
         "pay_period_end": "2023-07-30", "hours": "40", "wages": "1000"},
        {"employee_id": "A", "pay_date": "2024-08-09", "pay_period_start": "2024-07-29",
         "pay_period_end": "2024-08-04", "hours": "40", "wages": "1000"},
    ]
    selected, counts = select_rows(rows, date(2023, 7, 28), date(2024, 8, 2))
    check("BA-02 keeps a period starting before the window, paid inside it", len(selected), 1)
    check("BA-02 drops a period paid after the window", counts["excluded_pay_date_after_window"], 1)

    # BA-12 — the seven-day boundary, inclusive.
    check("BA-12 a 7-day period is real",
          is_real_pay_period({"pay_period_start": "2024-01-01", "pay_period_end": "2024-01-07"}), True)
    check("BA-12 a 6-day period is not",
          is_real_pay_period({"pay_period_start": "2024-01-01", "pay_period_end": "2024-01-06"}), False)

    # BA-11 — exclusive day count. A full year lands on 51.86, not 52.00.
    weeks, _ = min_max_weeks([
        {"pay_period_start": "2023-01-01", "pay_period_end": "2023-01-07"},
        {"pay_period_start": "2023-12-24", "pay_period_end": "2023-12-30"},
    ])
    check("BA-11 full year is 51.86 weeks, not 52.00", round_half_up(weeks, 2), Decimal("51.86"))

    # BA-03 — inclusive, and deduplicated on (start, end).
    pweeks, detail = period_weeks([
        {"pay_period_start": "2024-01-01", "pay_period_end": "2024-01-07", "hours": "40"},
        {"pay_period_start": "2024-01-01", "pay_period_end": "2024-01-07", "hours": "5"},
        {"pay_period_start": "2024-01-08", "pay_period_end": "2024-01-14", "hours": "40"},
    ])
    check("BA-03 two distinct periods are 2.00 weeks", round_half_up(pweeks, 2), Decimal("2.00"))
    check("BA-03 duplicate period counted once", detail["periods_counted"], 2)

    # BA-05 — negatives survive.
    totals = employee_totals([
        {"employee_id": "A", "pay_period_start": "2024-01-01", "pay_period_end": "2024-01-07",
         "hours": "40", "wages": "1000"},
        {"employee_id": "A", "pay_period_start": "2024-01-08", "pay_period_end": "2024-01-14",
         "hours": "-8", "wages": "-200"},
    ])
    check("BA-05 negative correction is retained", totals["A"]["total_hours"], Decimal("32"))

    # BA-06 — the rounded value is what the threshold tests.
    borderline = test_eligibility(
        {"total_hours": Decimal("1749.99"), "total_wages": Decimal("50000")},
        Decimal("50"),
    )
    check("BA-06 34.9998 rounds to 35.00 and qualifies on hours",
          borderline["rounded_avg_weekly_hours"], Decimal("35.00"))
    check("BA-06 and is therefore eligible", borderline["passed_hours"], True)

    # OZ-01 — month ends.
    check("OZ-01 twelve month ends from Aug 2023", month_end_targets(date(2023, 8, 31))[-1],
          date(2024, 7, 31))

    # OZ-04 — the Month 12 cliff, both sides.
    check("OZ-04 final period ending 12-16 moves the target",
          measuring_date(date(2024, 12, 31), date(2024, 12, 16), is_final_month=True),
          date(2024, 12, 16))
    check("OZ-04 final period ending 12-15 does not",
          measuring_date(date(2024, 12, 31), date(2024, 12, 15), is_final_month=True),
          date(2024, 12, 31))

    # OZ-07 — the divisor is twelve even when months are empty.
    summary = unit_summary([{"unit_id": "U1", "months": [Decimal("1")] * 6 + [Decimal("0")] * 6}])
    check("OZ-07 six months of 1 averages 0.50, not 1.00",
          summary[0]["average_headcount"], Decimal("0.50"))

    # Completeness — eleven of eleven reachable is complete.
    check("year_is_complete 11 of 11 reachable months", year_is_complete(11, 11), True)
    check("year_is_complete 11 of 12 reachable months", year_is_complete(11, 12), False)

    return results


if __name__ == "__main__":
    print(__doc__.strip().splitlines()[0].strip())
    print()
    outcomes = _self_check()
    width = max(len(name) for name, _, _ in outcomes)
    for name, ok, detail in outcomes:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}   {'' if ok else detail}")
    failed = sum(1 for _, ok, _ in outcomes if not ok)
    print()
    print(f"  {len(outcomes) - failed}/{len(outcomes)} passed")
    raise SystemExit(1 if failed else 0)
