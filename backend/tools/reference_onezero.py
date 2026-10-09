"""Reference Dataset One/Zero v1 with explicit proposed assumptions.

This benchmark-only implementation consumes ``ReferenceStep1Run`` eligibility
outputs. It does not alter the production One/Zero engine.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .reference_source import load_assumption_set_for_id
from .reference_step1 import CollapsedPayrollRow, ReferenceCalculationStep, ReferenceStep1Run

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Methodology sets are CONFIGURATION, not documentation. They were read from
# docs/data/ until a docs reorganisation moved them and the engine stopped
# booting - production code should never depend on the layout of a docs folder.
# They now live beside the rule packs they are versioned alongside.
_METHODOLOGY = Path(__file__).resolve().parent.parent / "rules" / "methodology"
_DEFAULT_ASSUMPTIONS = _METHODOLOGY / "reference-onezero-assumptions.v7.json"
_METHODOLOGY_WORKBOOK = _REPO_ROOT / "stakeholder-docs" / "GA JTC One Zero Methodology Overview.xlsx"
_HISTORICAL_WAGES_PDF = _REPO_ROOT / "stakeholder-docs" / "JTCHistoricalWages_Jul 2025.pdf"
_ASSUMPTION_PATHS = {
    "GDS-ONEZERO-2026-08-24-v7": _DEFAULT_ASSUMPTIONS,
}


def methodology_sources_present() -> bool:
    """Whether the private source documents this benchmark hashes into its
    provenance are staged in this checkout.

    `stakeholder-docs/` was removed from the repository (B05): the partner's
    methodology workbook and historical wages PDF do not ship and are not
    expected to be re-staged. A test exercising `run_reference_onezero` skips
    rather than fabricate a hash for a document it cannot read — see
    `tests/methodology_sources_gate.py`.
    """
    return _METHODOLOGY_WORKBOOK.exists() and _HISTORICAL_WAGES_PDF.exists()


# One/Zero v1-v6 are retired alongside their step-1 partners. The one/zero axis
# itself did not change at v8 — it holds no statutory values, only the month
# window and the headcount method — so it stays at v7 rather than taking a
# version bump that would imply a change nobody made.
RETIRED_ONEZERO_SETS = (
    "GDS-ONEZERO-2026-07-29-v1",
    "GDS-ONEZERO-2026-07-29-v2",
    "GDS-ONEZERO-2026-07-29-v3",
    "GDS-ONEZERO-2026-07-30-v4",
    "GDS-ONEZERO-2026-08-05-v5",
    "GDS-ONEZERO-2026-08-18-v6",
)

# Which one/zero set pairs with which step-1 set. Module-level so a test can
# register a variant pairing without reaching inside a function body.
STEP1_TO_ONEZERO: dict[str, str] = {
    "GDS-STEP1-2026-08-25-v8": "GDS-ONEZERO-2026-08-24-v7",
}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return "sha256:" + digest


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_onezero_assumption_set(path: Path = _DEFAULT_ASSUMPTIONS) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("assumption_set_id") not in _ASSUMPTION_PATHS:
        raise ValueError("unsupported Reference One/Zero assumption set")
    expected = {f"OZ-{index:02d}" for index in range(1, 10)}
    if set(payload.get("assumptions") or {}) != expected:
        raise ValueError("Reference One/Zero assumption set must contain OZ-01 through OZ-09")
    return payload


def load_onezero_assumption_set_for_id(assumption_set_id: str) -> tuple[dict[str, Any], Path]:
    try:
        path = _ASSUMPTION_PATHS[assumption_set_id]
    except KeyError as exc:
        raise ValueError("unsupported Reference One/Zero assumption set") from exc
    return load_onezero_assumption_set(path), path


def _month_ends(fiscal_begin: date) -> list[date]:
    months: list[date] = []
    year, month = fiscal_begin.year, fiscal_begin.month
    for _ in range(12):
        if month == 12:
            target = date(year, 12, 31)
            year, month = year + 1, 1
        else:
            target = date(year, month + 1, 1) - timedelta(days=1)
            month += 1
        months.append(target)
    return months


def _month_target(month_end: date, last_ppe: date, month_index: int) -> date:
    if (
        month_index == 11
        and last_ppe.year == month_end.year
        and last_ppe.month == month_end.month
        and last_ppe.day > 15
    ):
        return last_ppe
    return month_end


@dataclass
class ReferenceOneZeroMatrixRow:
    segment_id: str
    employee_id: str
    unit_id: str
    fein: str
    period_start: date
    period_end: date
    pay_date: date | None
    source_refs: list[tuple[str, int]]
    raw_months: list[int]
    months: list[int]

    def private_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "employee_id": self.employee_id,
            "unit_id": self.unit_id,
            "fein": self.fein,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "pay_date": self.pay_date.isoformat() if self.pay_date else None,
            "source_refs": [list(ref) for ref in self.source_refs],
            "raw_months": list(self.raw_months),
            "months": list(self.months),
        }


@dataclass
class ReferenceOneZeroSummaryRow:
    unit_id: str
    fein: str
    month_totals: list[int]
    total: int
    included_months: int
    unrounded_average: Decimal
    source_rounded_average: int
    application_average: Decimal

    def private_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["unrounded_average"] = str(self.unrounded_average)
        payload["application_average"] = str(self.application_average)
        return payload


@dataclass
class ReferenceOneZeroMethodResult:
    method: str
    months: list[date]
    matrix: list[ReferenceOneZeroMatrixRow] = field(repr=False)
    summary: list[ReferenceOneZeroSummaryRow] = field(repr=False)
    overlap_flags: list[dict[str, Any]] = field(repr=False)
    major_period_controls: dict[str, Any] | None = None

    def aggregate_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "months": [month.isoformat() for month in self.months],
            "matrix_rows": len(self.matrix),
            "units": len({(row.unit_id, row.fein) for row in self.summary}),
            "overlap_flags": len(self.overlap_flags),
            "monthly_counts_before_disposition": [
                sum(row.raw_months[index] for row in self.matrix) for index in range(12)
            ],
            "monthly_counts_after_disposition": [
                sum(row.months[index] for row in self.matrix) for index in range(12)
            ],
            "major_period_controls": self.major_period_controls,
        }


@dataclass
class ReferenceOneZeroRun:
    calculation_id: str
    step1_calculation_id: str
    step1_assumption_set_id: str
    onezero_assumption_set_id: str
    onezero_assumption_set_sha256: str
    methodology_workbook_sha256: str | None
    historical_wages_pdf_sha256: str | None
    min_max: ReferenceOneZeroMethodResult = field(repr=False)
    pay_period: ReferenceOneZeroMethodResult = field(repr=False)
    steps: list[ReferenceCalculationStep]
    exceptions: list[str]

    def summary_dict(self) -> dict[str, Any]:
        return {
            "calculation_id": self.calculation_id,
            "step1_calculation_id": self.step1_calculation_id,
            "step1_assumption_set_id": self.step1_assumption_set_id,
            "onezero_assumption_set_id": self.onezero_assumption_set_id,
            "onezero_assumption_set_sha256": self.onezero_assumption_set_sha256,
            "methodology_workbook_sha256": self.methodology_workbook_sha256,
            "historical_wages_pdf_sha256": self.historical_wages_pdf_sha256,
            "min_max": self.min_max.aggregate_dict(),
            "pay_period": self.pay_period.aggregate_dict(),
            "exceptions": list(self.exceptions),
            "steps": [step.to_dict() for step in self.steps],
        }

    def employee_drill(self, employee_id: str) -> dict[str, Any] | None:
        min_max_rows = [row.private_dict() for row in self.min_max.matrix if row.employee_id == employee_id]
        pay_period_rows = [row.private_dict() for row in self.pay_period.matrix if row.employee_id == employee_id]
        if not min_max_rows and not pay_period_rows:
            return None
        return {
            "calculation_id": self.calculation_id,
            "employee_id": employee_id,
            "months": [month.isoformat() for month in self.min_max.months],
            "min_max": min_max_rows,
            "pay_period": pay_period_rows,
            "overlap_flags": [
                flag
                for flag in self.min_max.overlap_flags + self.pay_period.overlap_flags
                if flag["employee_id"] == employee_id
            ],
        }


def _coverage(start: date, end: date, months: list[date]) -> list[int]:
    values: list[int] = []
    for index, month_end in enumerate(months):
        target = _month_target(month_end, end, index)
        values.append(int(start <= target <= end))
    return values


def _apply_test_of_twos(
    rows: list[ReferenceOneZeroMatrixRow],
    method: str,
) -> list[dict[str, Any]]:
    by_employee_month: dict[tuple[str, int], list[ReferenceOneZeroMatrixRow]] = defaultdict(list)
    for row in rows:
        for month_index, value in enumerate(row.raw_months):
            if value:
                by_employee_month[(row.employee_id, month_index)].append(row)

    flags: list[dict[str, Any]] = []
    for (employee_id, month_index), candidates in sorted(by_employee_month.items()):
        if len(candidates) <= 1:
            continue
        keeper = max(
            candidates,
            key=lambda row: (row.period_start, row.period_end, row.segment_id),
        )
        flags.append({
            "type": "test_of_twos",
            "method": method,
            "employee_id": employee_id,
            "month_index": month_index,
            "candidate_segment_ids": [row.segment_id for row in candidates],
            "kept_segment_id": keeper.segment_id,
            "decision_basis": "OZ-06 latest PPS, then PPE, then stable segment ID",
        })
        for row in candidates:
            if row is not keeper:
                row.months[month_index] = 0
    return flags


def _summaries(rows: list[ReferenceOneZeroMatrixRow], included_months: int = 12) -> list[ReferenceOneZeroSummaryRow]:
    by_unit: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * 12)
    for row in rows:
        for index, value in enumerate(row.months):
            by_unit[(row.unit_id, row.fein)][index] += value
    output: list[ReferenceOneZeroSummaryRow] = []
    for (unit_id, fein), month_totals in sorted(by_unit.items()):
        total = sum(month_totals)
        unrounded = Decimal(total) / Decimal(included_months)
        output.append(ReferenceOneZeroSummaryRow(
            unit_id=unit_id,
            fein=fein,
            month_totals=month_totals,
            total=total,
            included_months=included_months,
            unrounded_average=unrounded,
            source_rounded_average=int(unrounded.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            application_average=unrounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        ))
    return output


def _build_min_max(
    step1: ReferenceStep1Run,
    months: list[date],
    *,
    exclude_zero_hour_rows: bool = True,
    minimum_pay_period_days: int = 0,
) -> ReferenceOneZeroMethodResult:
    """One row per eligible employee, unit and FEIN, spanning their time there.

    One Zero Min Max.docx Step 5: "There should be one line per unit that the
    employee worked at... with its respective earliest PayPeriodStart and last
    PayPeriodEnd."

    Two filters shape the span and both must agree with the eligibility stage or
    the matrix will show dates that contradict the weeks-worked detail:

    * ``exclude_zero_hour_rows`` -- BA-11. Step 5 scopes segments to units the
      employee "worked at", which reads as positive hours, whereas Step 2's
      plain day count does not filter. The asymmetry is deliberate and recorded.
    * ``minimum_pay_period_days`` -- BA-12, the partner's sub-seven-day cleaning rule.
    """
    eligible = {employee_id for employee_id, row in step1.min_max.items() if row.eligible}
    spans: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source in step1.collapsed_rows:
        if source.employee_id not in eligible:
            continue
        if exclude_zero_hour_rows and source.hours <= 0:
            continue
        if (
            minimum_pay_period_days > 0
            and (source.pay_period_end - source.pay_period_start).days + 1
            < minimum_pay_period_days
        ):
            continue
        key = (source.employee_id, source.unit_id, source.fein)
        slot = spans.setdefault(key, {
            "start": source.pay_period_start,
            "end": source.pay_period_end,
            "source_refs": [],
        })
        slot["start"] = min(slot["start"], source.pay_period_start)
        slot["end"] = max(slot["end"], source.pay_period_end)
        slot["source_refs"].extend(source.source_refs)

    rows: list[ReferenceOneZeroMatrixRow] = []
    for (employee_id, unit_id, fein), span in sorted(spans.items()):
        segment_id = f"MM|{employee_id}|{unit_id}|{fein}"
        raw_months = _coverage(span["start"], span["end"], months)
        rows.append(ReferenceOneZeroMatrixRow(
            segment_id=segment_id,
            employee_id=employee_id,
            unit_id=unit_id,
            fein=fein,
            period_start=span["start"],
            period_end=span["end"],
            pay_date=None,
            source_refs=sorted(set(span["source_refs"])),
            raw_months=raw_months,
            months=list(raw_months),
        ))
    flags = _apply_test_of_twos(rows, "min_max")
    return ReferenceOneZeroMethodResult(
        method="min_max",
        months=months,
        matrix=rows,
        summary=_summaries(rows),
        overlap_flags=flags,
    )


def _major_periods(rows: list[CollapsedPayrollRow]) -> tuple[set[tuple[date, date, date, str]], dict[str, Any]]:
    employees_by_period: dict[tuple[date, date, date, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.hours > 0:
            employees_by_period[row.period_key()].add(row.employee_id)
    by_frequency: dict[str, list[tuple[tuple[date, date, date, str], int]]] = defaultdict(list)
    for key, employees in employees_by_period.items():
        by_frequency[key[3]].append((key, len(employees)))

    major: set[tuple[date, date, date, str]] = set()
    controls: dict[str, Any] = {"by_frequency": {}}
    for frequency, items in sorted(by_frequency.items()):
        counts = sorted(count for _, count in items)
        median = counts[len(counts) // 2]
        threshold = max(1, median // 2)
        selected = [key for key, count in items if count >= threshold]
        major.update(selected)
        controls["by_frequency"][frequency] = {
            "periods": len(items),
            "median_employee_count": median,
            "major_threshold": threshold,
            "major_periods": len(selected),
            "off_cycle_periods": len(items) - len(selected),
        }
    controls["total_periods"] = len(employees_by_period)
    controls["major_periods"] = len(major)
    return major, controls


def _collapse_onezero_periods(
    rows: list[CollapsedPayrollRow],
) -> tuple[list[CollapsedPayrollRow], dict[str, int]]:
    grouped: dict[tuple[str, str, str, date, date], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.employee_id,
            row.unit_id,
            row.fein,
            row.pay_period_start,
            row.pay_period_end,
        )
        slot = grouped.setdefault(key, {
            "hours": Decimal("0"),
            "wages": Decimal("0"),
            "pay_dates": set(),
            "frequencies": set(),
            "source_refs": [],
            "source_rows": 0,
        })
        slot["hours"] += row.hours
        slot["wages"] += row.wages
        slot["pay_dates"].add(row.pay_date)
        slot["frequencies"].add(row.pay_frequency_code)
        slot["source_refs"].extend(row.source_refs)
        slot["source_rows"] += 1

    output: list[CollapsedPayrollRow] = []
    conflicts = 0
    source_rows_collapsed = 0
    for (employee_id, unit_id, fein, pps, ppe), slot in sorted(grouped.items()):
        if len(slot["frequencies"]) != 1:
            conflicts += 1
            continue
        source_rows_collapsed += slot["source_rows"] - 1
        output.append(CollapsedPayrollRow(
            employee_id=employee_id,
            unit_id=unit_id,
            fein=fein,
            pay_period_start=pps,
            pay_period_end=ppe,
            pay_date=max(slot["pay_dates"]),
            pay_frequency_code=next(iter(slot["frequencies"])),
            hours=slot["hours"],
            wages=slot["wages"],
            source_refs=sorted(set(slot["source_refs"])),
        ))
    return output, {
        "input_rows": len(rows),
        "collapsed_period_rows": len(output),
        "same_span_rows_collapsed": source_rows_collapsed,
        "conflicting_frequency_periods": conflicts,
    }


def _build_pay_period(
    step1: ReferenceStep1Run,
    months: list[date],
    *,
    collapse_same_span: bool,
) -> ReferenceOneZeroMethodResult:
    eligible = {employee_id for employee_id, row in step1.pay_period.items() if row.eligible}
    period_rows, collapse_controls = (
        _collapse_onezero_periods(step1.collapsed_rows)
        if collapse_same_span
        else (step1.collapsed_rows, {
            "input_rows": len(step1.collapsed_rows),
            "collapsed_period_rows": len(step1.collapsed_rows),
            "same_span_rows_collapsed": 0,
            "conflicting_frequency_periods": 0,
        })
    )
    major, controls = _major_periods(period_rows)
    controls["period_collapse"] = collapse_controls
    controls["classification_status"] = (
        "diagnostic_not_signoff_ready" if collapse_same_span else "v1_proposed"
    )
    rows: list[ReferenceOneZeroMatrixRow] = []
    for source in sorted(
        period_rows,
        key=lambda row: (row.employee_id, row.pay_period_start, row.unit_id, row.fein, row.pay_date),
    ):
        if source.employee_id not in eligible or source.hours <= 0 or source.period_key() not in major:
            continue
        segment_id = (
            f"PP|{source.employee_id}|{source.unit_id}|{source.fein}|"
            f"{source.pay_period_start.isoformat()}|{source.pay_period_end.isoformat()}|"
            f"{source.pay_date.isoformat()}|{source.pay_frequency_code}"
        )
        raw_months = _coverage(source.pay_period_start, source.pay_period_end, months)
        rows.append(ReferenceOneZeroMatrixRow(
            segment_id=segment_id,
            employee_id=source.employee_id,
            unit_id=source.unit_id,
            fein=source.fein,
            period_start=source.pay_period_start,
            period_end=source.pay_period_end,
            pay_date=source.pay_date,
            source_refs=list(source.source_refs),
            raw_months=raw_months,
            months=list(raw_months),
        ))
    flags = _apply_test_of_twos(rows, "pay_period")
    return ReferenceOneZeroMethodResult(
        method="pay_period",
        months=months,
        matrix=rows,
        summary=_summaries(rows),
        overlap_flags=flags,
        major_period_controls=controls,
    )


def run_reference_onezero(step1: ReferenceStep1Run) -> ReferenceOneZeroRun:
    try:
        onezero_assumption_set_id = STEP1_TO_ONEZERO[step1.assumption_set_id]
    except KeyError as exc:
        raise ValueError(
            f"no One/Zero assumption set paired with {step1.assumption_set_id}"
        ) from exc
    assumption_set, assumption_path = load_onezero_assumption_set_for_id(
        onezero_assumption_set_id
    )
    step1_config = load_assumption_set_for_id(step1.assumption_set_id)
    window_config = assumption_set["assumptions"]["OZ-01"].get("config") or {}
    window_begin = window_config.get("month_window_begin")
    if window_begin:
        months = _month_ends(date.fromisoformat(window_begin))
    else:
        months = _month_ends(
            date.fromisoformat(
                step1_config["assumptions"]["BA-01"]["config"]["fiscal_year_begin"]
            )
        )
    min_max = _build_min_max(
        step1,
        months,
        exclude_zero_hour_rows=bool(
            step1_config["assumptions"]
            .get("BA-11", {})
            .get("config", {})
            .get("onezero_segment_excludes_zero_hour_rows", True)
        ),
        minimum_pay_period_days=int(
            step1_config["assumptions"]
            .get("BA-12", {})
            .get("config", {})
            .get("minimum_pay_period_days", 0)
        )
        if step1_config["assumptions"]
        .get("BA-12", {})
        .get("config", {})
        .get("applies_to_onezero_segment_span", False)
        else 0,
    )
    pay_period = _build_pay_period(
        step1,
        months,
        collapse_same_span=not onezero_assumption_set_id.endswith("-v1"),
    )
    assumption_hash = _hash_file(assumption_path)
    # stakeholder-docs/ was removed from the repository (B05): the partner's
    # methodology workbook and historical wages PDF do not ship and are not
    # expected to be re-staged (methodology_sources_present() above). A
    # version that never cited one of them still records None; a version
    # that did now also records None once the file is gone, rather than
    # raising FileNotFoundError on every call - this is a live runtime path
    # (the sealed workspace), not only a test fixture.
    methodology_workbook_hash = (
        _hash_file(_METHODOLOGY_WORKBOOK)
        if not onezero_assumption_set_id.endswith("-v1") and _METHODOLOGY_WORKBOOK.exists()
        else None
    )
    historical_wages_pdf_hash = (
        _hash_file(_HISTORICAL_WAGES_PDF)
        if onezero_assumption_set_id.endswith(("-v3", "-v4", "-v5", "-v6", "-v7"))
        and _HISTORICAL_WAGES_PDF.exists()
        else None
    )
    calculation_id = _hash_json({
        "step1_calculation_id": step1.calculation_id,
        "onezero_assumption_set_sha256": assumption_hash,
        "methodology_workbook_sha256": methodology_workbook_hash,
        "historical_wages_pdf_sha256": historical_wages_pdf_hash,
    })
    exceptions = ["OZ-03 Pay Period range coverage remains pending Access validation."]
    if not onezero_assumption_set_id.endswith("-v1"):
        exceptions.extend([
            "OZ-05 major-cycle classifier is diagnostic only; sign-off requires reviewed company or Access cycle evidence.",
            "OZ-06 test-of-twos disposition remains provisional until reviewed.",
            "OZ-07 partial-year denominator and rounding views remain pending validation.",
        ])
    else:
        exceptions.extend([
            "OZ-02 Min-Max range coverage is proposed pending the partner's validation.",
            "OZ-05 major-period classifier is proposed pending Access period output.",
            "OZ-06 test-of-twos tie-break is proposed pending the partner's disposition.",
            "OZ-07 partial-year denominator and rounding views are pending validation.",
        ])
    steps = [
        ReferenceCalculationStep(
            step_id="GDS.ONEZERO.MIN_MAX.MATRIX",
            stage="matrix",
            method="min_max",
            inputs={"eligible_employees": sum(row.eligible for row in step1.min_max.values())},
            input_counts={"matrix_rows": len(min_max.matrix)},
            parameters={"months": [month.isoformat() for month in months]},
            formula="one row per eligible employee-unit-FEIN; 1 when earliest PPS <= month target <= latest PPE",
            output=min_max.aggregate_dict(),
            decision_basis="source_confirmed_with_proposed_assumptions",
            assumption_ids=["OZ-01", "OZ-02", "OZ-04", "OZ-06", "OZ-08", "OZ-09"],
            exceptions=["coverage fields and test-of-twos disposition pending validation"],
            citation="One Zero Min Max.docx Step 5",
        ),
        ReferenceCalculationStep(
            step_id="GDS.ONEZERO.PAY_PERIOD.MATRIX",
            stage="matrix",
            method="pay_period",
            inputs={"eligible_employees": sum(row.eligible for row in step1.pay_period.values())},
            input_counts={"matrix_rows": len(pay_period.matrix)},
            parameters={
                "months": [month.isoformat() for month in months],
                "major_period_controls": pay_period.major_period_controls,
            },
            formula="one row per eligible employee-major-period-unit-FEIN; 1 when PPS <= month target <= PPE",
            output=pay_period.aggregate_dict(),
            decision_basis="source_confirmed_with_proposed_assumptions",
            assumption_ids=["OZ-01", "OZ-03", "OZ-04", "OZ-05", "OZ-06", "OZ-08", "OZ-09"],
            exceptions=["source equality wording treated as period-range example; classifier is diagnostic only"],
            citation="One Zero Pay Periods.docx Steps 2 and 6; GA JTC One Zero Methodology Overview.xlsx rows 48-52",
        ),
        ReferenceCalculationStep(
            step_id="GDS.ONEZERO.SUMMARY",
            stage="summary",
            method="both",
            inputs={
                "min_max_matrix_rows": len(min_max.matrix),
                "pay_period_matrix_rows": len(pay_period.matrix),
            },
            input_counts={
                "min_max_units": len(min_max.summary),
                "pay_period_units": len(pay_period.summary),
            },
            parameters={"included_months": 12, "precision_views": ["unrounded", "source_whole", "application_2dp"]},
            formula="unit month totals=sum employee counts; average=total/included months",
            output={
                "min_max": min_max.aggregate_dict(),
                "pay_period": pay_period.aggregate_dict(),
            },
            decision_basis="source_confirmed_with_proposed_assumption",
            assumption_ids=["OZ-07"],
            exceptions=["partial-year denominator pending future case"],
            citation="One Zero Min Max.docx Step 6; One Zero Pay Periods.docx Step 7",
        ),
    ]
    return ReferenceOneZeroRun(
        calculation_id=calculation_id,
        step1_calculation_id=step1.calculation_id,
        step1_assumption_set_id=step1.assumption_set_id,
        onezero_assumption_set_id=assumption_set["assumption_set_id"],
        onezero_assumption_set_sha256=assumption_hash,
        methodology_workbook_sha256=methodology_workbook_hash,
        historical_wages_pdf_sha256=historical_wages_pdf_hash,
        min_max=min_max,
        pay_period=pay_period,
        steps=steps,
        exceptions=exceptions,
    )
