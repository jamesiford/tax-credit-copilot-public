"""Reference Dataset Step 1 eligibility calculations with explicit provenance.

The module is private-benchmark infrastructure. It implements the approved
GDS-STEP1-2026-07-29-v1 assumptions without changing production One/Zero code.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .reference_source import (
    ReferencePayrollRow,
    ReferenceSourceSnapshot,
    load_assumption_set_for_id,
    statutory_floors_for,
)

_TWO_PLACES = Decimal("0.01")


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _round_two(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass
class ReferenceCalculationStep:
    step_id: str
    stage: str
    method: str
    inputs: dict[str, Any]
    input_counts: dict[str, int]
    parameters: dict[str, Any]
    formula: str
    output: dict[str, Any]
    decision_basis: str
    assumption_ids: list[str]
    exceptions: list[str]
    citation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CollapsedPayrollRow:
    employee_id: str
    unit_id: str
    fein: str
    pay_period_start: date
    pay_period_end: date
    pay_date: date
    pay_frequency_code: str
    hours: Decimal
    wages: Decimal
    source_refs: list[tuple[str, int]] = field(default_factory=list)

    def period_key(self) -> tuple[date, date, date, str]:
        return (
            self.pay_period_start,
            self.pay_period_end,
            self.pay_date,
            self.pay_frequency_code,
        )


@dataclass(frozen=True)
class EmployeeTotals:
    employee_id: str
    total_hours: Decimal
    total_wages: Decimal


@dataclass(frozen=True)
class EmployeeEligibility:
    employee_id: str
    method: str
    total_hours: Decimal
    total_wages: Decimal
    denominator_weeks: Decimal
    avg_weekly_hours: Decimal
    avg_weekly_wages: Decimal
    rounded_avg_weekly_hours: Decimal
    rounded_avg_weekly_wages: Decimal
    passed_hours: bool
    passed_wages: bool
    eligible: bool
    denominator_detail: dict[str, Any]

    def private_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "total_hours",
            "total_wages",
            "denominator_weeks",
            "avg_weekly_hours",
            "avg_weekly_wages",
            "rounded_avg_weekly_hours",
            "rounded_avg_weekly_wages",
        ):
            payload[key] = _decimal_text(payload[key])
        return payload


@dataclass
class ReferenceStep1Run:
    calculation_id: str
    assumption_set_id: str
    assumption_set_sha256: str
    source_manifest_sha256: str
    selection_counts: dict[str, int]
    boundary_controls: dict[str, Any]
    collapse_counts: dict[str, int]
    common_totals: dict[str, EmployeeTotals] = field(repr=False)
    min_max: dict[str, EmployeeEligibility] = field(repr=False)
    pay_period: dict[str, EmployeeEligibility] = field(repr=False)
    collapsed_rows: list[CollapsedPayrollRow] = field(repr=False)
    steps: list[ReferenceCalculationStep]
    exceptions: list[str]
    review_tolerance_weeks: Decimal = Decimal("1.5")
    maximum_weeks_without_review: Decimal = Decimal("52")
    short_period_exclusions: dict[str, Any] = field(default_factory=dict)

    def denominator_invariant(self) -> dict[str, Any]:
        deltas = {
            employee_id: self.pay_period[employee_id].denominator_weeks
            - self.min_max[employee_id].denominator_weeks
            for employee_id in self.common_totals
        }
        positive = [delta for delta in deltas.values() if delta > 0]
        tolerance = self.review_tolerance_weeks
        maximum_weeks = self.maximum_weeks_without_review
        return {
            "employees_evaluated": len(deltas),
            "pay_period_gt_min_max": len(positive),
            "pay_period_gt_min_max_over_review_tolerance": sum(
                delta > tolerance for delta in positive
            ),
            "pay_period_over_52_weeks": sum(
                row.denominator_weeks > maximum_weeks for row in self.pay_period.values()
            ),
            "maximum_excess_weeks": _decimal_text(max(positive, default=Decimal("0"))),
            "review_tolerance_weeks": _decimal_text(tolerance),
            "maximum_weeks_without_review": _decimal_text(maximum_weeks),
            "repair_policy": "none",
            "invariant_holds": not positive,
        }

    def pay_period_controls(self) -> dict[str, int]:
        details = [row.denominator_detail for row in self.pay_period.values()]
        return {
            "source_period_keys": sum(item.get("source_period_key_count", 0) for item in details),
            "employee_pps_ppe_periods": sum(item.get("collapsed_period_count", 0) for item in details),
            "same_pps_ppe_records_collapsed": sum(
                item.get("same_pps_ppe_records_collapsed", 0) for item in details
            ),
            "conflicting_frequency_periods": sum(
                len(item.get("conflicting_frequency_periods", [])) for item in details
            ),
        }

    def summary_dict(self) -> dict[str, Any]:
        min_max_ids = {employee_id for employee_id, row in self.min_max.items() if row.eligible}
        pay_period_ids = {employee_id for employee_id, row in self.pay_period.items() if row.eligible}
        return {
            "calculation_id": self.calculation_id,
            "assumption_set_id": self.assumption_set_id,
            "assumption_set_sha256": self.assumption_set_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "selection_counts": self.selection_counts,
            "boundary_controls": self.boundary_controls,
            "collapse_counts": self.collapse_counts,
            "employees_with_totals": len(self.common_totals),
            "min_max": {
                "employees_evaluated": len(self.min_max),
                "eligible_employees": len(min_max_ids),
            },
            "pay_period": {
                "employees_evaluated": len(self.pay_period),
                "eligible_employees": len(pay_period_ids),
            },
            "eligibility_reconciliation": {
                "eligible_both": len(min_max_ids & pay_period_ids),
                "min_max_only": len(min_max_ids - pay_period_ids),
                "pay_period_only": len(pay_period_ids - min_max_ids),
            },
            "pay_period_controls": self.pay_period_controls(),
            "short_period_exclusions": self.short_period_exclusions,
            "denominator_invariant": self.denominator_invariant(),
            "exceptions": list(self.exceptions),
            "steps": [step.to_dict() for step in self.steps],
        }

    def employee_drill(self, employee_id: str) -> dict[str, Any] | None:
        totals = self.common_totals.get(employee_id)
        if totals is None:
            return None
        source_rows = [row for row in self.collapsed_rows if row.employee_id == employee_id]
        return {
            "calculation_id": self.calculation_id,
            "assumption_set_id": self.assumption_set_id,
            "employee_id": employee_id,
            "source_rows": [
                {
                    "unit_id": row.unit_id,
                    "fein": row.fein,
                    "pay_period_start": row.pay_period_start.isoformat(),
                    "pay_period_end": row.pay_period_end.isoformat(),
                    "pay_date": row.pay_date.isoformat(),
                    "pay_frequency_code": row.pay_frequency_code,
                    "hours": _decimal_text(row.hours),
                    "wages": _decimal_text(row.wages),
                    "source_refs": [list(ref) for ref in row.source_refs],
                }
                for row in sorted(source_rows, key=lambda item: (item.pay_period_start, item.unit_id))
            ],
            "totals": {
                "total_hours": _decimal_text(totals.total_hours),
                "total_wages": _decimal_text(totals.total_wages),
            },
            "min_max": self.min_max.get(employee_id).private_dict() if employee_id in self.min_max else None,
            "pay_period": self.pay_period.get(employee_id).private_dict() if employee_id in self.pay_period else None,
            "denominator_invariant": {
                "pay_period_minus_min_max_weeks": _decimal_text(
                    self.pay_period[employee_id].denominator_weeks
                    - self.min_max[employee_id].denominator_weeks
                ),
                "pay_period_gt_min_max": self.pay_period[employee_id].denominator_weeks
                > self.min_max[employee_id].denominator_weeks,
                "over_review_tolerance": self.pay_period[employee_id].denominator_weeks
                > self.min_max[employee_id].denominator_weeks + Decimal("1.5"),
                "pay_period_over_52_weeks": self.pay_period[employee_id].denominator_weeks
                > Decimal("52"),
            },
        }


def _select_rows(
    rows: list[ReferencePayrollRow],
    fiscal_begin: date,
    fiscal_end: date,
    *,
    include_prior_ppe_paid_in_fy: bool = False,
    exclude_ppe_after_fy_end: bool = True,
) -> tuple[list[ReferencePayrollRow], dict[str, int]]:
    selected: list[ReferencePayrollRow] = []
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        if row.pay_date < fiscal_begin:
            counts["excluded_pay_date_before_fy"] += 1
        elif row.pay_date > fiscal_end:
            counts["excluded_pay_date_after_fy"] += 1
        elif row.pay_period_end > fiscal_end and exclude_ppe_after_fy_end:
            counts["excluded_ppe_after_fy"] += 1
        elif row.pay_period_end < fiscal_begin and not include_prior_ppe_paid_in_fy:
            counts["excluded_ppe_before_fy"] += 1
        else:
            selected.append(row)
            counts["included"] += 1
            if row.pay_period_end > fiscal_end:
                counts["included_ppe_after_fy_end"] += 1
            if row.pay_period_end < fiscal_begin:
                counts["included_prior_ppe_paid_in_fy"] += 1
            if row.pay_period_start < fiscal_begin <= row.pay_period_end:
                counts["included_transcends_fy_start"] += 1
    counts["input"] = len(rows)
    return selected, dict(counts)


def _boundary_controls(
    rows: list[ReferencePayrollRow],
    fiscal_begin: date,
    fiscal_end: date,
) -> dict[str, Any]:
    valid_rows = [row for row in rows if row.pay_period_start <= row.pay_period_end]
    prior_ppe = [
        row for row in valid_rows
        if row.pay_period_end < fiscal_begin
        and fiscal_begin <= row.pay_date <= fiscal_end
    ]
    crossing_start = [
        row for row in valid_rows
        if row.pay_period_start < fiscal_begin <= row.pay_period_end
        and fiscal_begin <= row.pay_date <= fiscal_end
    ]
    trailing = [
        row for row in valid_rows
        if row.pay_period_end <= fiscal_end and row.pay_date > fiscal_end
    ]
    pre_fy = [row for row in valid_rows if row.pay_period_start < fiscal_begin]
    earliest_pps = min((row.pay_period_start for row in valid_rows), default=None)
    earliest_pay_date = min((row.pay_date for row in valid_rows), default=None)
    has_lookback = bool(pre_fy)
    return {
        "status": "LEADING_LOOKBACK_PRESENT" if has_lookback else "MISSING_LEADING_LOOKBACK",
        "boundary_complete": has_lookback and bool(prior_ppe or crossing_start),
        "earliest_valid_pay_period_start": earliest_pps.isoformat() if earliest_pps else None,
        "earliest_valid_pay_date": earliest_pay_date.isoformat() if earliest_pay_date else None,
        "valid_pre_fy_pps_rows": len(pre_fy),
        "valid_pre_fy_pps_employees": len({row.employee_id for row in pre_fy}),
        "prior_ppe_paid_in_fy_rows": len(prior_ppe),
        "prior_ppe_paid_in_fy_employees": len({row.employee_id for row in prior_ppe}),
        "crossing_start_rows": len(crossing_start),
        "crossing_start_employees": len({row.employee_id for row in crossing_start}),
        "current_ppe_paid_after_fy_rows": len(trailing),
        "current_ppe_paid_after_fy_employees": len({row.employee_id for row in trailing}),
        "synthetic_boundary_rows_added": 0,
        "force_52_weeks": False,
    }


def _collapse_rows(rows: list[ReferencePayrollRow]) -> tuple[list[CollapsedPayrollRow], dict[str, int]]:
    grouped: dict[tuple[str, str, str, date, date, date, str], CollapsedPayrollRow] = {}
    for row in rows:
        key = row.collapse_key()
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = CollapsedPayrollRow(
                employee_id=row.employee_id,
                unit_id=row.unit_id,
                fein=row.fein,
                pay_period_start=row.pay_period_start,
                pay_period_end=row.pay_period_end,
                pay_date=row.pay_date,
                pay_frequency_code=row.pay_frequency_code,
                hours=row.hours,
                wages=row.wages,
                source_refs=[(row.source_file, row.source_row)],
            )
        else:
            existing.hours += row.hours
            existing.wages += row.wages
            existing.source_refs.append((row.source_file, row.source_row))
    collapsed = list(grouped.values())
    return collapsed, {
        "input_rows": len(rows),
        "collapsed_rows": len(collapsed),
        "duplicate_rows_collapsed": len(rows) - len(collapsed),
        "multi_line_groups": sum(len(row.source_refs) > 1 for row in collapsed),
    }


def _qualifies_as_pay_period(
    row: CollapsedPayrollRow,
    minimum_pay_period_days: int,
) -> bool:
    """Is this row's pay period long enough to be treated as a real pay period?

    BA-12. The partner, 2026-08-12: "Before performing any additional
    analysis, I remove pay periods that are only 1 to 6 days long, as these
    generally do not represent 'real' pay periods."

    Applied to the numerator, the Min-Max span, and the Pay Period denominator
    alike. A threshold of 0 disables the rule, which is how assumption sets v1
    through v5 replay unchanged.
    """
    if minimum_pay_period_days <= 0:
        return True
    return (row.pay_period_end - row.pay_period_start).days + 1 >= minimum_pay_period_days


def _build_totals(
    rows: list[CollapsedPayrollRow],
    minimum_pay_period_days: int = 0,
) -> dict[str, EmployeeTotals]:
    """Sum each employee's eligible hours and wages -- the shared numerator.

    Sources: One Zero Min Max.docx Step 1; One Zero Pay Periods.docx Step 1.
    Both say simply "add up the total hours and total wages for each employee",
    so totals are customer-wide; unit and FEIN are ignored until One/Zero
    allocation.

    Signed corrections are preserved and zero-hour wage rows are retained
    (BA-05). When BA-12 is active, rows in sub-threshold pay periods are
    excluded here as well as from the denominator -- see the note on that
    assumption for why the partner's own output contradicts their description of the
    numerator.
    """
    totals: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    for row in rows:
        if not _qualifies_as_pay_period(row, minimum_pay_period_days):
            continue
        totals[row.employee_id][0] += row.hours
        totals[row.employee_id][1] += row.wages
    return {
        employee_id: EmployeeTotals(employee_id, values[0], values[1])
        for employee_id, values in totals.items()
    }


def _eligibility(
    *,
    employee_id: str,
    method: str,
    totals: EmployeeTotals,
    weeks: Decimal,
    detail: dict[str, Any],
    hours_floor: Decimal,
    wages_floor: Decimal,
) -> EmployeeEligibility:
    if weeks <= 0:
        avg_hours = avg_wages = Decimal("0")
    else:
        avg_hours = totals.total_hours / weeks
        avg_wages = totals.total_wages / weeks
    rounded_hours = _round_two(avg_hours)
    rounded_wages = _round_two(avg_wages)
    passed_hours = weeks > 0 and rounded_hours >= hours_floor
    passed_wages = weeks > 0 and rounded_wages >= wages_floor
    return EmployeeEligibility(
        employee_id=employee_id,
        method=method,
        total_hours=totals.total_hours,
        total_wages=totals.total_wages,
        denominator_weeks=weeks,
        avg_weekly_hours=avg_hours,
        avg_weekly_wages=avg_wages,
        rounded_avg_weekly_hours=rounded_hours,
        rounded_avg_weekly_wages=rounded_wages,
        passed_hours=passed_hours,
        passed_wages=passed_wages,
        eligible=passed_hours and passed_wages,
        denominator_detail=detail,
    )


def _run_min_max(
    rows: list[CollapsedPayrollRow],
    totals: dict[str, EmployeeTotals],
    hours_floor: Decimal,
    wages_floor: Decimal,
    *,
    inclusive_days: bool = True,
    exclude_zero_hour_rows: bool = True,
    minimum_pay_period_days: int = 0,
) -> dict[str, EmployeeEligibility]:
    """Min-Max eligibility: one continuous span per employee.

    One Zero Min Max.docx Step 2: "Using the earliest PayPeriodStart date for
    each employee and the latest PayPeriodEnd date for each employee, count the
    number of days between the two and divide by 7."

    Two readings of that sentence matter and both are configurable:

    * ``inclusive_days`` -- whether the end day is counted. BA-11 reads "days
      between" literally as exclusive, so a full-year weekly employee lands on
      51.86 weeks rather than 52.00. The partner's 2026-08-12 reconciliation confirmed
      the exclusive reading, reproducing their weeks for 8 of their 9 employees.
    * ``minimum_pay_period_days`` -- BA-12, above. Short periods are dropped
      before the span is measured, which is what moved several of the partner's
      employees' Min and Max dates relative to ours.

    Step 3 then divides the Step 1 totals by these weeks; Step 4 applies the
    floors. An employee with no qualifying period yields zero weeks and is
    reported rather than silently dropped.
    """
    work_rows: dict[str, list[CollapsedPayrollRow]] = defaultdict(list)
    for row in rows:
        if exclude_zero_hour_rows and row.hours <= 0:
            continue
        if not _qualifies_as_pay_period(row, minimum_pay_period_days):
            continue
        work_rows[row.employee_id].append(row)
    output: dict[str, EmployeeEligibility] = {}
    for employee_id, employee_totals in totals.items():
        employee_rows = work_rows.get(employee_id, [])
        if employee_rows:
            first_start = min(row.pay_period_start for row in employee_rows)
            last_end = max(row.pay_period_end for row in employee_rows)
            span_days = (last_end - first_start).days + (1 if inclusive_days else 0)
            weeks = Decimal(span_days) / Decimal("7")
            detail = {
                "first_start": first_start.isoformat(),
                "last_end": last_end.isoformat(),
                "span_days": span_days,
                "span_mode": "inclusive_days" if inclusive_days else "exclusive_days",
                "excludes_zero_hour_rows": exclude_zero_hour_rows,
                "minimum_pay_period_days": minimum_pay_period_days,
                "hire_term_caps_available": False,
            }
            if inclusive_days:
                detail["inclusive_days"] = span_days
        else:
            weeks = Decimal("0")
            detail = {
                "reason": "no_qualifying_pay_period"
                if minimum_pay_period_days > 0
                else "no_positive_hour_periods"
                if exclude_zero_hour_rows
                else "no_dated_periods",
                "minimum_pay_period_days": minimum_pay_period_days,
            }
        output[employee_id] = _eligibility(
            employee_id=employee_id,
            method="min_max",
            totals=employee_totals,
            weeks=weeks,
            detail=detail,
            hours_floor=hours_floor,
            wages_floor=wages_floor,
        )
    return output


def _run_pay_period(
    rows: list[CollapsedPayrollRow],
    totals: dict[str, EmployeeTotals],
    frequency_weeks: dict[str, Decimal],
    hours_floor: Decimal,
    wages_floor: Decimal,
    *,
    denominator_mode: str = "frequency_code",
    count_zero_hour_periods: bool = False,
    minimum_pay_period_days: int = 0,
) -> dict[str, EmployeeEligibility]:
    """Pay Period eligibility: weeks accumulated period by period.

    One Zero Pay Periods.docx Step 3 counts "the number of weeks that an
    employee worked", counting unique pay periods only, and caps a person at 53
    weeks. Step 4 divides the Step 1 totals by that count.

    ``denominator_mode`` selects how each period contributes:

    * ``frequency_code`` -- the literal reading of the source's "Frequency =
      Weeks in Pay Period" definition, mapping codes 1/2/4 to that many weeks.
      Retained for replay of v1 through v4.
    * ``actual_span_inclusive`` -- BA-03 v5 onwards. Each period contributes its
      own ``(end - start + 1) / 7``. Adopted because the codes do not behave as
      documented: all 1,364 code-4 periods run the 16th to the 31st (16 days)
      and code-2 periods are predominantly the 1st to the 15th, which is a
      semi-monthly cycle rather than four- and two-week ones. The literal
      reading yields 447 eligible against the partner's reported 659; actual span
      yields 664.

    Multiple source rows sharing an employee's PPS/PPE collapse to one
    denominator period, with every source row retained as lineage.
    """
    periods: dict[str, dict[tuple[date, date], dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if not _qualifies_as_pay_period(row, minimum_pay_period_days):
            continue
        period_key = (row.pay_period_start, row.pay_period_end)
        slot = periods[row.employee_id].setdefault(period_key, {
            "hours": Decimal("0"),
            "frequencies": set(),
            "pay_dates": set(),
            "source_period_keys": set(),
        })
        slot["hours"] += row.hours
        slot["frequencies"].add(row.pay_frequency_code)
        slot["pay_dates"].add(row.pay_date)
        slot["source_period_keys"].add(row.period_key())

    output: dict[str, EmployeeEligibility] = {}
    for employee_id, employee_totals in totals.items():
        included: list[dict[str, Any]] = []
        weeks = Decimal("0")
        cadence_counts: Counter[str] = Counter()
        conflicts: list[dict[str, Any]] = []
        employee_periods = periods.get(employee_id, {})
        for (pps, ppe), period in employee_periods.items():
            if period["hours"] <= 0 and not count_zero_hour_periods:
                continue
            frequencies = sorted(period["frequencies"])
            if len(frequencies) != 1:
                conflicts.append({
                    "pay_period_start": pps.isoformat(),
                    "pay_period_end": ppe.isoformat(),
                    "frequency_codes": frequencies,
                })
                if denominator_mode != "actual_span_inclusive":
                    continue
            frequency = frequencies[0] if len(frequencies) == 1 else "|".join(frequencies)
            if denominator_mode == "actual_span_inclusive":
                period_weeks = Decimal((ppe - pps).days + 1) / Decimal("7")
            else:
                if frequency not in frequency_weeks:
                    raise ValueError(f"unconfigured PayFrequency value {frequency!r}")
                period_weeks = frequency_weeks[frequency]
            included.append({
                "pay_period_start": pps.isoformat(),
                "pay_period_end": ppe.isoformat(),
                "pay_frequency_code": frequency,
                "period_weeks": _decimal_text(period_weeks),
                "pay_dates": [value.isoformat() for value in sorted(period["pay_dates"])],
                "source_period_key_count": len(period["source_period_keys"]),
            })
            cadence_counts[frequency] += 1
            weeks += period_weeks
        source_period_key_count = sum(
            len(item["source_period_keys"]) for item in employee_periods.values()
        )
        detail = {
            "included_period_count": len(included),
            "denominator_mode": denominator_mode,
            "counts_zero_hour_periods": count_zero_hour_periods,
            "cadence_counts": dict(sorted(cadence_counts.items())),
            "source_period_key_count": source_period_key_count,
            "collapsed_period_count": len(employee_periods),
            "same_pps_ppe_records_collapsed": source_period_key_count - len(employee_periods),
            "conflicting_frequency_periods": conflicts,
            "period_keys": sorted(
                included,
                key=lambda item: (item["pay_period_start"], item["pay_period_end"]),
            ),
        }
        output[employee_id] = _eligibility(
            employee_id=employee_id,
            method="pay_period",
            totals=employee_totals,
            weeks=weeks,
            detail=detail,
            hours_floor=hours_floor,
            wages_floor=wages_floor,
        )
    return output


def _short_period_exclusions(
    rows: list[CollapsedPayrollRow],
    minimum_pay_period_days: int,
) -> dict[str, Any]:
    """Report every row excluded by BA-12 so it can be reviewed, never silently dropped.

    The partner, 2026-08-20, asked for exactly this: "maybe you capture the
    ineligibles and then give the user the ability to review the ineligibles and
    say, well, wait a minute, that one should be eligible. Let's put it back over
    there", and "we should have some sort of like an exception report... that
    says, yes, this client had this weird thing going on".

    The engine treats exclusions as a soft delete: the rows stay addressable via
    their source file and row number, and the hours and wages they carry are
    still counted in the numerator.
    """
    if minimum_pay_period_days <= 0:
        return {"minimum_pay_period_days": 0, "excluded_rows": 0}

    by_length: Counter[int] = Counter()
    excluded_hours = Decimal("0")
    excluded_wages = Decimal("0")
    affected: set[str] = set()
    employees_with_any_valid: set[str] = set()
    for row in rows:
        days = (row.pay_period_end - row.pay_period_start).days + 1
        if days < minimum_pay_period_days:
            by_length[days] += 1
            excluded_hours += row.hours
            excluded_wages += row.wages
            affected.add(row.employee_id)
        else:
            employees_with_any_valid.add(row.employee_id)
    return {
        "minimum_pay_period_days": minimum_pay_period_days,
        "excluded_rows": sum(by_length.values()),
        "excluded_rows_by_period_length": dict(sorted(by_length.items())),
        "excluded_hours": _decimal_text(excluded_hours),
        "excluded_wages": _decimal_text(excluded_wages),
        "employees_touched": len(affected),
        "employees_left_with_no_valid_period": len(affected - employees_with_any_valid),
        "numerator_treatment": "retained",
        "disposition": "soft_delete_reviewable",
    }


def run_reference_step1(snapshot: ReferenceSourceSnapshot) -> ReferenceStep1Run:
    """Run the approved Step 1 assumptions against a scanned private source."""
    assumption_set = load_assumption_set_for_id(snapshot.assumption_set_id)
    if assumption_set["assumption_set_id"] != snapshot.assumption_set_id:
        raise ValueError("source snapshot and calculation assumption sets differ")
    config = assumption_set["assumptions"]
    fiscal_begin = date.fromisoformat(config["BA-01"]["config"]["fiscal_year_begin"])
    fiscal_end = date.fromisoformat(config["BA-01"]["config"]["fiscal_year_end"])
    frequency_weeks = {
        code: Decimal(str(value))
        for code, value in (
            config["BA-03"]["config"].get("pay_frequency_weeks")
            or config["BA-03"]["config"].get("pay_frequency_weeks_reference_only")
            or {}
        ).items()
    }
    denominator_mode = config["BA-03"]["config"].get(
        "pay_period_denominator_mode", "frequency_code"
    )
    count_zero_hour_periods = bool(
        config["BA-05"]["config"].get("count_zero_hour_only_period_as_worked_period", False)
    )
    min_max_config = config.get("BA-11", {}).get("config", {})
    min_max_inclusive_days = min_max_config.get("min_max_span_mode", "inclusive_days") != "exclusive_days"
    min_max_exclude_zero_hour = bool(
        min_max_config.get("min_max_excludes_zero_hour_rows", True)
    )
    # BA-12: the partner's short-pay-period cleaning rule. Absent (v1-v5) the threshold
    # is 0, which disables the filter and leaves historical replays untouched.
    short_period_config = config.get("BA-12", {}).get("config", {})
    minimum_pay_period_days = int(short_period_config.get("minimum_pay_period_days", 0))
    short_period_in_numerator = bool(short_period_config.get("applies_to_numerator", False))
    short_period_in_min_max = bool(short_period_config.get("applies_to_min_max_span", False))
    short_period_in_pay_period = bool(
        short_period_config.get("applies_to_pay_period_denominator", False)
    )
    floors = statutory_floors_for(assumption_set)
    hours_floor = Decimal(str(floors.min_weekly_hours))
    wages_floor = Decimal(str(floors.min_weekly_wages))

    boundary_controls = _boundary_controls(snapshot.rows, fiscal_begin, fiscal_end)
    selected, selection_counts = _select_rows(
        snapshot.rows,
        fiscal_begin,
        fiscal_end,
        include_prior_ppe_paid_in_fy=bool(
            config["BA-02"]["config"].get("include_prior_fy_ppe_paid_in_fiscal_year", False)
        ),
        exclude_ppe_after_fy_end=bool(
            config["BA-02"]["config"].get("pay_period_end_must_not_exceed_fiscal_year_end", True)
        ),
    )
    collapsed, collapse_counts = _collapse_rows(selected)
    totals = _build_totals(
        collapsed,
        minimum_pay_period_days if short_period_in_numerator else 0,
    )
    min_max = _run_min_max(
        collapsed,
        totals,
        hours_floor,
        wages_floor,
        inclusive_days=min_max_inclusive_days,
        exclude_zero_hour_rows=min_max_exclude_zero_hour,
        minimum_pay_period_days=minimum_pay_period_days if short_period_in_min_max else 0,
    )
    pay_period = _run_pay_period(
        collapsed,
        totals,
        frequency_weeks,
        hours_floor,
        wages_floor,
        denominator_mode=denominator_mode,
        count_zero_hour_periods=count_zero_hour_periods,
        minimum_pay_period_days=minimum_pay_period_days if short_period_in_pay_period else 0,
    )

    denominator_deltas = [
        pay_period[employee_id].denominator_weeks - min_max[employee_id].denominator_weeks
        for employee_id in totals
    ]
    positive_deltas = [delta for delta in denominator_deltas if delta > 0]
    review_tolerance = Decimal(
        str(config.get("BA-09", {}).get("config", {}).get("review_tolerance_weeks", 1.5))
    )
    max_weeks_without_review = Decimal(
        str(
            config.get("BA-09", {})
            .get("config", {})
            .get("maximum_pay_period_weeks_without_review", 52.0)
        )
    )
    denominator_invariant = {
        "employees_evaluated": len(denominator_deltas),
        "pay_period_gt_min_max": len(positive_deltas),
        "pay_period_gt_min_max_over_review_tolerance": sum(
            delta > review_tolerance for delta in positive_deltas
        ),
        "pay_period_over_52_weeks": sum(
            row.denominator_weeks > max_weeks_without_review for row in pay_period.values()
        ),
        "maximum_excess_weeks": _decimal_text(max(positive_deltas, default=Decimal("0"))),
        "repair_policy": "none",
    }

    source_manifest = snapshot.manifest_dict()
    short_period_exclusions = _short_period_exclusions(collapsed, minimum_pay_period_days)
    source_manifest_sha256 = _hash_json(source_manifest)
    calculation_id = _hash_json({
        "source_manifest_sha256": source_manifest_sha256,
        "assumption_set_sha256": snapshot.assumption_set_sha256,
    })
    exceptions = [
        "BA-06 rounding_mode is not Access-verified; the current implementation uses ROUND_HALF_UP.",
        "Hire/termination caps are unavailable in the supplied source.",
        "Pay codes are unavailable; all supplied wages are treated as eligible compensation.",
        f"BA-09 review required for {len(positive_deltas)} employees where Pay Period weeks exceed Min-Max weeks.",
    ]
    if boundary_controls["status"] == "MISSING_LEADING_LOOKBACK":
        exceptions.append(
            "BA-10 source boundary is incomplete: no valid pre-FY payroll lookback was supplied; denominators are not forced to 52 weeks."
        )

    common_parameters = {
        "fiscal_begin": fiscal_begin.isoformat(),
        "fiscal_end": fiscal_end.isoformat(),
        "hours_floor": _decimal_text(hours_floor),
        "wages_floor": _decimal_text(wages_floor),
        # Where the floors came from. A trail that records $636 without naming the
        # year pack it was resolved from cannot answer "which statute did you
        # apply?", which is the question an audit actually asks. [ADR-005]
        "statutory_source": floors.as_dict()["source"],
        "statutory_program_code": floors.program_code,
        "statutory_tax_year": floors.tax_year,
    }
    steps = [
        ReferenceCalculationStep(
            step_id="GDS.SOURCE.SELECT",
            stage="source",
            method="shared",
            inputs={"source_manifest_sha256": source_manifest_sha256},
            input_counts={"rows": snapshot.controls.usable_rows},
            parameters={"fiscal_begin": fiscal_begin.isoformat(), "fiscal_end": fiscal_end.isoformat()},
            formula=(
                "include when FY_BEGIN <= PayDate <= FY_END and PPE <= FY_END; "
                "v4 permits PPE < FY_BEGIN"
                if "BA-10" in config
                else "include when FY_BEGIN <= PayDate <= FY_END and FY_BEGIN <= PPE <= FY_END"
            ),
            output=selection_counts,
            decision_basis="project_assumption",
            assumption_ids=["BA-01", "BA-02", "BA-08"],
            exceptions=[],
            citation="Georgia JTC Step 1 Avg Wages and Hours Narrative Steps 1-2",
        ),
        *(
            [ReferenceCalculationStep(
                step_id="GDS.SOURCE.BOUNDARY_COMPLETENESS",
                stage="source",
                method="shared",
                inputs={
                    "fiscal_begin": fiscal_begin.isoformat(),
                    "fiscal_end": fiscal_end.isoformat(),
                    "usable_rows": snapshot.controls.usable_rows,
                },
                input_counts={"rows": snapshot.controls.usable_rows},
                parameters={
                    "include_prior_fy_ppe_paid_in_fiscal_year": True,
                    "synthetic_boundary_rows_allowed": False,
                    "force_52_weeks": False,
                },
                formula="report leading/trailing boundary coverage; never synthesize rows or force denominator weeks",
                output=boundary_controls,
                decision_basis="source_gap_control",
                assumption_ids=["BA-02", "BA-10"],
                exceptions=(
                    ["missing valid pre-FY payroll lookback"]
                    if boundary_controls["status"] == "MISSING_LEADING_LOOKBACK"
                    else []
                ),
                citation="Georgia JTC Step 1 Avg Wages and Hours Narrative Step 1; GDS-56/57",
            )]
            if "BA-10" in config
            else []
        ),
        ReferenceCalculationStep(
            step_id="GDS.SOURCE.COLLAPSE",
            stage="normalize",
            method="shared",
            inputs={"included_rows": selection_counts.get("included", 0)},
            input_counts={"rows": len(selected)},
            parameters={"collapse_key": config["BA-04"]["config"]["collapse_key"]},
            formula="group by BA-04 key; sum signed Hours and Wages",
            output=collapse_counts,
            decision_basis="project_assumption",
            assumption_ids=["BA-04", "BA-05"],
            exceptions=["pay codes unavailable"],
            citation="Georgia JTC Step 1 Avg Wages and Hours Narrative Step 3",
        ),
        ReferenceCalculationStep(
            step_id="GDS.EMPLOYEE.TOTALS",
            stage="total",
            method="shared",
            inputs={"collapsed_rows": len(collapsed)},
            input_counts={"employees": len(totals)},
            parameters={},
            formula="TotalHours = sum(signed Hours); TotalWages = sum(signed Wages) by employee",
            output={"employees": len(totals)},
            decision_basis="source_confirmed",
            assumption_ids=["BA-05"],
            exceptions=[],
            citation="One Zero Pay Periods.docx Step 1; One Zero Min Max.docx Step 1",
        ),
        ReferenceCalculationStep(
            step_id="GDS.ELIGIBILITY.MIN_MAX",
            stage="eligibility",
            method="min_max",
            inputs={"employees": len(totals)},
            input_counts={"employees_evaluated": len(min_max)},
            parameters=common_parameters,
            formula="weeks=(last PPE-first PPS+1)/7; averages=totals/weeks; test rounded averages",
            output={"eligible_employees": sum(row.eligible for row in min_max.values())},
            decision_basis="source_confirmed_with_project_assumption",
            assumption_ids=["BA-05", "BA-06"],
            exceptions=["hire/term caps unavailable", "rounding mode not Access-verified"],
            citation="Georgia JTC Step 1 Narrative Steps 5-8; One Zero Min Max.docx Steps 2-4",
        ),
        ReferenceCalculationStep(
            step_id="GDS.ELIGIBILITY.PAY_PERIOD",
            stage="eligibility",
            method="pay_period",
            inputs={"employees": len(totals)},
            input_counts={"employees_evaluated": len(pay_period)},
            parameters={**common_parameters, "frequency_weeks": {key: _decimal_text(value) for key, value in frequency_weeks.items()}},
            formula="weeks=sum(source cadence factors for unique positive-hour periods); averages=totals/weeks; test rounded averages",
            output={"eligible_employees": sum(row.eligible for row in pay_period.values())},
            decision_basis="source_confirmed_with_project_assumption",
            assumption_ids=["BA-03", "BA-05", "BA-06"],
            exceptions=["rounding mode not Access-verified"],
            citation="Georgia JTC Step 1 Narrative Steps 5-8; One Zero Pay Periods.docx Steps 3-5",
        ),
        ReferenceCalculationStep(
            step_id="GDS.ELIGIBILITY.RECONCILE",
            stage="reconciliation",
            method="both",
            inputs={"employees": len(totals)},
            input_counts={"employees_evaluated": len(denominator_deltas)},
            parameters={
                "review_tolerance_weeks": "1.5",
                "maximum_pay_period_weeks_without_review": "52",
                "repair_policy": "none",
            },
            formula="report PayPeriodWeeks > MinMaxWeeks and PayPeriodWeeks > 52; do not repair",
            output=denominator_invariant,
            decision_basis="source_confirmed_review_control",
            assumption_ids=["BA-03", "BA-09"],
            exceptions=["major-cycle groups remain pending reviewed company or Access evidence"],
            citation="GA JTC One Zero Methodology Overview.xlsx rows 48-52",
        ),
    ]

    return ReferenceStep1Run(
        calculation_id=calculation_id,
        assumption_set_id=snapshot.assumption_set_id,
        assumption_set_sha256=snapshot.assumption_set_sha256,
        source_manifest_sha256=source_manifest_sha256,
        selection_counts=selection_counts,
        boundary_controls=boundary_controls,
        collapse_counts=collapse_counts,
        common_totals=totals,
        min_max=min_max,
        pay_period=pay_period,
        collapsed_rows=collapsed,
        steps=steps,
        exceptions=exceptions,
        review_tolerance_weeks=review_tolerance,
        maximum_weeks_without_review=max_weeks_without_review,
        short_period_exclusions=short_period_exclusions,
    )
