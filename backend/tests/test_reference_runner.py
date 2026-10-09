"""Reference Dataset local runner and report privacy tests."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from methodology_sources_gate import pytestmark  # noqa: F401
from tools.reference_runner import run
from tools.reference_source import TCC_COLUMNS


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=TCC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_runner_writes_aggregate_and_private_outputs_separately(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    row = {
        "TCCEmployeeId": "PRIVATE_E1",
        "Tax Year": "2024",
        "JobTitle": "Analyst",
        "TCCUnitId": "PRIVATE_U1",
        "PayPeriodStart": "8/1/2023",
        "PayPeriodEnd": "8/7/2023",
        "PaycheckDate": "8/10/2023",
        "PayFrequency": "1",
        "FEIN": "PRIVATE_F1",
        "Hours": "35",
        "Wages": "686",
    }
    _write(source / "One.csv", [row])
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(source / name, [])

    summary = run(source, output, employee_id="PRIVATE_E1")

    expected = {
        "source_manifest.json",
        "step1_summary.json",
        "common_employee_totals.csv",
        "min_max_eligibility.csv",
        "pay_period_eligibility.csv",
        "eligibility_discrepancies.csv",
        "onezero_summary.json",
        "min_max_onezero_matrix.csv",
        "pay_period_onezero_matrix.csv",
        "min_max_onezero_summary.csv",
        "pay_period_onezero_summary.csv",
        "onezero_overlap_flags.json",
        "employee_drill.json",
    }
    assert {path.name for path in output.iterdir()} == expected
    assert summary["min_max"]["eligible_employees"] == 1
    assert summary["pay_period"]["eligible_employees"] == 1
    assert summary["onezero"]["min_max"]["matrix_rows"] == 1
    assert summary["onezero"]["pay_period"]["matrix_rows"] == 1
    assert summary["run_metadata"]["private_output"] is True
    assert summary["run_metadata"]["code_commit"]

    aggregate = (output / "step1_summary.json").read_text(encoding="utf-8")
    onezero_aggregate = (output / "onezero_summary.json").read_text(encoding="utf-8")
    manifest = (output / "source_manifest.json").read_text(encoding="utf-8")
    assert "PRIVATE_E1" not in aggregate
    assert "PRIVATE_E1" not in onezero_aggregate
    assert "PRIVATE_E1" not in manifest
    assert "PRIVATE_F1" not in manifest

    totals = (output / "common_employee_totals.csv").read_text(encoding="utf-8")
    drill = json.loads((output / "employee_drill.json").read_text(encoding="utf-8"))
    assert "PRIVATE_E1" in totals
    assert drill["step1"]["employee_id"] == "PRIVATE_E1"
    assert drill["step1"]["min_max"]["eligible"] is True
    assert drill["step1"]["pay_period"]["eligible"] is True
    assert len(drill["onezero"]["min_max"]) == 1
    assert len(drill["onezero"]["pay_period"]) == 1
