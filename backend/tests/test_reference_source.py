"""Reference Dataset TCC adapter tests with no committed private source rows."""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from assumption_variants import runnable_set
from tools.reference_source import TCC_COLUMNS, TccPayrollAdapter


def _v4(tmp_path: Path) -> Path:
    """The v4 methodology, made runnable under the year-pack statute seam."""
    return runnable_set("v4", tmp_path)


def _write_chunk(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=TCC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "TCCEmployeeId": "E1",
        "Tax Year": "2024",
        "JobTitle": "Analyst",
        "TCCUnitId": "U1",
        "PayPeriodStart": "8/1/2023",
        "PayPeriodEnd": "8/7/2023",
        "PaycheckDate": "8/10/2023",
        "PayFrequency": "1",
        "FEIN": "F1",
        "Hours": "40",
        "Wages": "800.25",
    }
    row.update(overrides)
    return row


@pytest.fixture
def tcc_source(tmp_path: Path) -> Path:
    _write_chunk(tmp_path / "One.csv", [_row(), {column: "" for column in TCC_COLUMNS}])
    _write_chunk(
        tmp_path / "Two.csv",
        [
            _row(Hours="-2", Wages="-40.25"),
            _row(
                TCCEmployeeId="E2",
                TCCUnitId="U2",
                FEIN="F2",
                PayPeriodStart="7/25/2024",
                PayPeriodEnd="7/31/2024",
                PaycheckDate="8/9/2024",
                PayFrequency="2",
                Hours="0",
                Wages="500",
            ),
        ],
    )
    _write_chunk(tmp_path / "Three.csv", [])
    _write_chunk(tmp_path / "Four.csv", [])
    return tmp_path


def test_adapter_preserves_order_lineage_and_decimal_values(tcc_source: Path):
    snapshot = TccPayrollAdapter(source_dir=tcc_source).scan()

    assert [row.source_file for row in snapshot.rows] == ["One.csv", "Two.csv", "Two.csv"]
    assert [row.source_row for row in snapshot.rows] == [2, 2, 3]
    assert snapshot.rows[0].hours == Decimal("40")
    assert snapshot.rows[0].wages == Decimal("800.25")
    assert snapshot.rows[1].hours == Decimal("-2")
    assert snapshot.rows[1].wages == Decimal("-40.25")

    mapped = snapshot.rows[0].to_engine_dict()
    assert mapped["Employee_ID"] == "E1"
    assert mapped["Worksite_ID"] == "U1"
    assert mapped["Pay_Period_Start"] == "2023-08-01"
    assert mapped["Pay_Date"] == "2023-08-10"
    assert mapped["_Source_File"] == "One.csv"
    assert mapped["_Source_Row"] == 2
    assert mapped["_Source_Pay_Frequency"] == "1"


def test_scan_emits_safe_manifest_and_quality_controls(tcc_source: Path):
    snapshot = TccPayrollAdapter(source_dir=tcc_source).scan()
    controls = snapshot.controls

    assert controls.physical_rows == 4
    assert controls.usable_rows == 3
    assert controls.padded_rows == 1
    assert controls.invalid_rows == 0
    assert controls.zero_hour_rows == 1
    assert controls.negative_hour_rows == 1
    assert controls.negative_wage_rows == 1
    assert controls.duplicate_groups == 1
    assert controls.duplicate_group_rows == 2
    assert controls.post_fiscal_year_paycheck_rows == 1
    assert controls.distinct_employees == 2
    assert controls.distinct_units == 2
    assert controls.distinct_feins == 2
    assert controls.earliest_period_start == "2023-08-01"
    assert controls.latest_period_end == "2024-07-31"

    manifest_json = json.dumps(snapshot.manifest_dict(), sort_keys=True)
    assert "E1" not in manifest_json
    assert "F1" not in manifest_json
    assert snapshot.assumption_set_id == "GDS-STEP1-2026-08-25-v8"
    assert snapshot.assumption_set_sha256.startswith("sha256:")


def test_missing_required_values_are_flagged_not_silently_dropped(tmp_path: Path):
    invalid = _row(TCCEmployeeId="")
    _write_chunk(tmp_path / "One.csv", [invalid])
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write_chunk(tmp_path / name, [])

    snapshot = TccPayrollAdapter(source_dir=tmp_path, assumption_path=_v4(tmp_path)).scan()

    assert snapshot.controls.invalid_rows == 1
    assert snapshot.controls.usable_rows == 0
    assert snapshot.exceptions == [
        {
            "type": "missing_required_value",
            "source_file": "One.csv",
            "source_row": 2,
            "fields": ["TCCEmployeeId"],
        }
    ]


def test_private_source_controls_match_documented_aggregates():
    source_dir = Path(__file__).resolve().parent.parent / "data" / "payroll"
    if not all((source_dir / name).exists() for name in ("One.csv", "Two.csv", "Three.csv", "Four.csv")):
        pytest.skip("private Reference Dataset is not present")

    controls = TccPayrollAdapter(source_dir=source_dir).scan().controls

    assert controls.physical_rows == 488_968
    assert controls.padded_rows == 104_535
    assert controls.usable_rows == 384_433
    assert controls.invalid_rows == 0
    assert controls.distinct_employees == 10_236
    assert controls.distinct_units == 101
    assert controls.distinct_feins == 2
    assert controls.zero_hour_rows == 129_619
    assert controls.negative_hour_rows == 247
    assert controls.negative_wage_rows == 417
    assert controls.pay_date_before_period_end_rows == 2_981
    # v5 trims on paycheck date only against a 2024-08-02 fiscal end, which
    # reproduces the partner's reported 384,418 post-trim records exactly
    # (384,433 usable less these 15 rows).
    assert controls.post_fiscal_year_paycheck_rows == 15
    assert controls.usable_rows - controls.post_fiscal_year_paycheck_rows == 384_418
    assert controls.earliest_period_start == "2023-08-01"
    assert controls.latest_period_end == "2024-07-31"
    assert controls.earliest_pay_date == "2023-08-03"
    assert controls.latest_pay_date == "2024-08-09"
