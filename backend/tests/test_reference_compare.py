"""Reference Access output import and hierarchical reconciliation tests."""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from methodology_sources_gate import pytestmark  # noqa: F401
from tools.reference_compare import compare_access_bundle, load_access_bundle
from tools.reference_onezero import run_reference_onezero
from tools.reference_runner import write_private_report
from tools.reference_source import TCC_COLUMNS, TccPayrollAdapter
from tools.reference_step1 import run_reference_step1


def _write_source(path: Path) -> None:
    rows = [
        {
            "TCCEmployeeId": "E1", "Tax Year": "2024", "JobTitle": "A",
            "TCCUnitId": "U1", "PayPeriodStart": "8/1/2023",
            "PayPeriodEnd": "8/7/2023", "PaycheckDate": "8/10/2023",
            "PayFrequency": "1", "FEIN": "F1", "Hours": "40", "Wages": "700",
        },
        {
            "TCCEmployeeId": "E1", "Tax Year": "2024", "JobTitle": "A",
            "TCCUnitId": "U1", "PayPeriodStart": "8/8/2023",
            "PayPeriodEnd": "8/14/2023", "PaycheckDate": "8/17/2023",
            "PayFrequency": "1", "FEIN": "F1", "Hours": "40", "Wages": "700",
        },
    ]
    with (path / "One.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=TCC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        with (path / name).open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=TCC_COLUMNS)
            writer.writeheader()


def _runs(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    snapshot = TccPayrollAdapter(source_dir=source).scan()
    step1 = run_reference_step1(snapshot)
    onezero = run_reference_onezero(step1)
    return snapshot, step1, onezero


def test_generated_private_csv_bundle_reconciles_cleanly(tmp_path: Path):
    snapshot, step1, onezero = _runs(tmp_path)
    bundle = tmp_path / "bundle"
    write_private_report(step1, onezero, snapshot.manifest_dict(), bundle)

    access = load_access_bundle(bundle)
    report = compare_access_bundle(access, step1, onezero)

    assert report["stages_compared"] == [
        "common_employee_totals",
        "min_max_eligibility",
        "pay_period_eligibility",
        "min_max_onezero_summary",
        "pay_period_onezero_summary",
    ]
    assert report["first_divergent_stage"] is None
    assert report["reconciled"] is True
    assert all(stage["difference_count"] == 0 for stage in report["stages"])


def test_comparator_reports_first_divergent_stage_and_field(tmp_path: Path):
    snapshot, step1, onezero = _runs(tmp_path)
    bundle = tmp_path / "bundle"
    write_private_report(step1, onezero, snapshot.manifest_dict(), bundle)

    totals_path = bundle / "common_employee_totals.csv"
    rows = list(csv.DictReader(totals_path.open(newline="", encoding="utf-8")))
    rows[0]["TotalHours"] = "79.00"
    with totals_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    report = compare_access_bundle(load_access_bundle(bundle), step1, onezero)

    assert report["first_divergent_stage"] == "common_employee_totals"
    assert report["reconciled"] is False
    first = report["stages"][0]
    assert first["difference_count"] == 1
    assert first["differences"][0]["key"] == ["E1"]
    assert first["differences"][0]["field"] == "TotalHours"
    assert first["differences"][0]["difference"] == "1.00"


def test_xlsx_import_accepts_john_style_sheet_and_header_aliases(tmp_path: Path):
    _, step1, onezero = _runs(tmp_path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Total Hours and Wages"
    sheet.append(["TCCEmployeeId", "Total Hours", "Total Wages"])
    sheet.append(["E1", 80, 1400])

    min_max = workbook.create_sheet("Min Max Eligibility")
    min_max.append([
        "EmployeeID", "TotalHours", "TotalWages", "Weeks", "AvgWeeklyHours",
        "AvgWeeklyWage", "Hours Test Pass", "Wage Test Pass", "Overall Eligible",
    ])
    row = step1.min_max["E1"]
    min_max.append([
        "E1", float(row.total_hours), float(row.total_wages),
        float(row.denominator_weeks), float(row.rounded_avg_weekly_hours),
        float(row.rounded_avg_weekly_wages), 1, 1, 1,
    ])
    path = tmp_path / "john-results.xlsx"
    workbook.save(path)

    access = load_access_bundle(path)
    report = compare_access_bundle(access, step1, onezero)

    assert set(access) == {"common_employee_totals", "min_max_eligibility"}
    assert report["stages_compared"] == ["common_employee_totals", "min_max_eligibility"]
    assert report["reconciled"] is True


def test_numeric_tolerance_allows_one_cent_difference(tmp_path: Path):
    snapshot, step1, onezero = _runs(tmp_path)
    bundle = tmp_path / "bundle"
    write_private_report(step1, onezero, snapshot.manifest_dict(), bundle)
    totals_path = bundle / "common_employee_totals.csv"
    rows = list(csv.DictReader(totals_path.open(newline="", encoding="utf-8")))
    rows[0]["TotalWages"] = "1400.01"
    with totals_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    report = compare_access_bundle(load_access_bundle(bundle), step1, onezero)

    assert report["reconciled"] is True
    assert report["first_divergent_stage"] is None
