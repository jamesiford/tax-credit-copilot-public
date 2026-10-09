"""Local-only Reference Dataset Step 1 runner and private report writer.

Run from ``backend/`` with ``python -m tools.reference_runner``. Console output is
aggregate-only; employee-level outputs are written under the gitignored output
folder.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .reference_onezero import ReferenceOneZeroMethodResult, ReferenceOneZeroRun, run_reference_onezero
from .reference_source import TccPayrollAdapter
from .reference_step1 import EmployeeEligibility, EmployeeTotals, ReferenceStep1Run, run_reference_step1

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SOURCE = _BACKEND_ROOT / "data" / "payroll"
_DEFAULT_OUTPUT = _BACKEND_ROOT / "data" / "reference_output"
_REPO_ROOT = _BACKEND_ROOT.parent


def _code_commit() -> str:
    configured = os.getenv("GIT_COMMIT")
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _totals_rows(totals: dict[str, EmployeeTotals]) -> Iterable[dict[str, Any]]:
    for employee_id in sorted(totals):
        row = totals[employee_id]
        yield {
            "Employee_ID": employee_id,
            "TotalHours": str(row.total_hours),
            "TotalWages": str(row.total_wages),
        }


def _eligibility_rows(rows: dict[str, EmployeeEligibility]) -> Iterable[dict[str, Any]]:
    for employee_id in sorted(rows):
        row = rows[employee_id]
        yield {
            "Employee_ID": employee_id,
            "Method": row.method,
            "TotalHours": str(row.total_hours),
            "TotalWages": str(row.total_wages),
            "DenominatorWeeks": str(row.denominator_weeks),
            "AvgWeeklyHoursFull": str(row.avg_weekly_hours),
            "AvgWeeklyWagesFull": str(row.avg_weekly_wages),
            "AvgWeeklyHours": str(row.rounded_avg_weekly_hours),
            "AvgWeeklyWages": str(row.rounded_avg_weekly_wages),
            "PassedHours": int(row.passed_hours),
            "PassedWages": int(row.passed_wages),
            "Eligible": int(row.eligible),
            "DenominatorDetail": json.dumps(row.denominator_detail, sort_keys=True),
        }


def _discrepancy_rows(run: ReferenceStep1Run) -> Iterable[dict[str, Any]]:
    for employee_id in sorted(set(run.min_max) | set(run.pay_period)):
        min_max = run.min_max.get(employee_id)
        pay_period = run.pay_period.get(employee_id)
        if min_max is None or pay_period is None or min_max.eligible != pay_period.eligible:
            yield {
                "Employee_ID": employee_id,
                "MinMaxEligible": "" if min_max is None else int(min_max.eligible),
                "PayPeriodEligible": "" if pay_period is None else int(pay_period.eligible),
                "MinMaxWeeks": "" if min_max is None else str(min_max.denominator_weeks),
                "PayPeriodWeeks": "" if pay_period is None else str(pay_period.denominator_weeks),
                "MinMaxAvgHours": "" if min_max is None else str(min_max.rounded_avg_weekly_hours),
                "PayPeriodAvgHours": "" if pay_period is None else str(pay_period.rounded_avg_weekly_hours),
                "MinMaxAvgWages": "" if min_max is None else str(min_max.rounded_avg_weekly_wages),
                "PayPeriodAvgWages": "" if pay_period is None else str(pay_period.rounded_avg_weekly_wages),
            }


def _matrix_rows(result: ReferenceOneZeroMethodResult) -> Iterable[dict[str, Any]]:
    month_fields = [f"Month{index}" for index in range(1, 13)]
    for row in result.matrix:
        payload = {
            "Segment_ID": row.segment_id,
            "Employee_ID": row.employee_id,
            "Unit_ID": row.unit_id,
            "FEIN": row.fein,
            "Period_Start": row.period_start.isoformat(),
            "Period_End": row.period_end.isoformat(),
            "Pay_Date": row.pay_date.isoformat() if row.pay_date else "",
            "Source_Refs": json.dumps(row.source_refs),
            "Raw_Months": json.dumps(row.raw_months),
        }
        payload.update(dict(zip(month_fields, row.months)))
        yield payload


def _summary_rows(result: ReferenceOneZeroMethodResult) -> Iterable[dict[str, Any]]:
    month_fields = [f"Month{index}" for index in range(1, 13)]
    for row in result.summary:
        payload = {
            "Unit_ID": row.unit_id,
            "FEIN": row.fein,
            "Total": row.total,
            "Included_Months": row.included_months,
            "Unrounded_Average": str(row.unrounded_average),
            "Source_Rounded_Average": row.source_rounded_average,
            "Application_Average": str(row.application_average),
        }
        payload.update(dict(zip(month_fields, row.month_totals)))
        yield payload


def write_private_report(
    run: ReferenceStep1Run,
    onezero: ReferenceOneZeroRun,
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    employee_id: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "calculation_id": run.calculation_id,
        "assumption_set_id": run.assumption_set_id,
        "assumption_set_sha256": run.assumption_set_sha256,
        "source_manifest_sha256": run.source_manifest_sha256,
        "code_commit": _code_commit(),
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "private_output": True,
    }
    summary = {**run.summary_dict(), "onezero": onezero.summary_dict(), "run_metadata": metadata}
    _write_json(output_dir / "source_manifest.json", manifest)
    _write_json(output_dir / "step1_summary.json", summary)
    _write_json(output_dir / "onezero_summary.json", onezero.summary_dict())
    _write_csv(
        output_dir / "common_employee_totals.csv",
        ["Employee_ID", "TotalHours", "TotalWages"],
        _totals_rows(run.common_totals),
    )
    eligibility_fields = [
        "Employee_ID",
        "Method",
        "TotalHours",
        "TotalWages",
        "DenominatorWeeks",
        "AvgWeeklyHoursFull",
        "AvgWeeklyWagesFull",
        "AvgWeeklyHours",
        "AvgWeeklyWages",
        "PassedHours",
        "PassedWages",
        "Eligible",
        "DenominatorDetail",
    ]
    _write_csv(output_dir / "min_max_eligibility.csv", eligibility_fields, _eligibility_rows(run.min_max))
    _write_csv(output_dir / "pay_period_eligibility.csv", eligibility_fields, _eligibility_rows(run.pay_period))
    discrepancy_fields = [
        "Employee_ID",
        "MinMaxEligible",
        "PayPeriodEligible",
        "MinMaxWeeks",
        "PayPeriodWeeks",
        "MinMaxAvgHours",
        "PayPeriodAvgHours",
        "MinMaxAvgWages",
        "PayPeriodAvgWages",
    ]
    _write_csv(
        output_dir / "eligibility_discrepancies.csv",
        discrepancy_fields,
        _discrepancy_rows(run),
    )
    matrix_fields = [
        "Segment_ID", "Employee_ID", "Unit_ID", "FEIN", "Period_Start",
        "Period_End", "Pay_Date", "Source_Refs", "Raw_Months",
        *[f"Month{index}" for index in range(1, 13)],
    ]
    summary_fields = [
        "Unit_ID", "FEIN", *[f"Month{index}" for index in range(1, 13)],
        "Total", "Included_Months", "Unrounded_Average",
        "Source_Rounded_Average", "Application_Average",
    ]
    _write_csv(output_dir / "min_max_onezero_matrix.csv", matrix_fields, _matrix_rows(onezero.min_max))
    _write_csv(output_dir / "pay_period_onezero_matrix.csv", matrix_fields, _matrix_rows(onezero.pay_period))
    _write_csv(output_dir / "min_max_onezero_summary.csv", summary_fields, _summary_rows(onezero.min_max))
    _write_csv(output_dir / "pay_period_onezero_summary.csv", summary_fields, _summary_rows(onezero.pay_period))
    _write_json(output_dir / "onezero_overlap_flags.json", {
        "min_max": onezero.min_max.overlap_flags,
        "pay_period": onezero.pay_period.overlap_flags,
    })
    if employee_id:
        step1_drill = run.employee_drill(employee_id)
        onezero_drill = onezero.employee_drill(employee_id)
        if step1_drill is None and onezero_drill is None:
            raise KeyError("employee not present in selected Reference Dataset rows")
        _write_json(output_dir / "employee_drill.json", {
            "step1": step1_drill,
            "onezero": onezero_drill,
        })
    return summary


def run(
    source_dir: Path = _DEFAULT_SOURCE,
    output_dir: Path = _DEFAULT_OUTPUT,
    *,
    employee_id: str | None = None,
) -> dict[str, Any]:
    snapshot = TccPayrollAdapter(source_dir=source_dir).scan()
    step1 = run_reference_step1(snapshot)
    onezero = run_reference_onezero(step1)
    return write_private_report(
        step1,
        onezero,
        snapshot.manifest_dict(),
        output_dir,
        employee_id=employee_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the private Reference Dataset Step 1 benchmark.")
    parser.add_argument("--source-dir", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--employee", dest="employee_id", help="Write one private employee drill; value is never printed.")
    args = parser.parse_args()
    summary = run(args.source_dir, args.output_dir, employee_id=args.employee_id)
    safe_console = {
        "calculation_id": summary["calculation_id"],
        "assumption_set_id": summary["assumption_set_id"],
        "source_manifest_sha256": summary["source_manifest_sha256"],
        "selection_counts": summary["selection_counts"],
        "employees_with_totals": summary["employees_with_totals"],
        "min_max": summary["min_max"],
        "pay_period": summary["pay_period"],
        "eligibility_reconciliation": summary["eligibility_reconciliation"],
        "onezero": {
            "calculation_id": summary["onezero"]["calculation_id"],
            "assumption_set_id": summary["onezero"]["onezero_assumption_set_id"],
            "min_max": summary["onezero"]["min_max"],
            "pay_period": summary["onezero"]["pay_period"],
        },
        "output_dir": str(args.output_dir),
    }
    print(json.dumps(safe_console, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
