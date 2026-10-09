"""Reference Dataset One/Zero v1 matrix, overlap, summary, and provenance tests."""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from assumption_variants import runnable_set
from methodology_sources_gate import pytestmark  # noqa: F401
from tools.reference_onezero import run_reference_onezero
from tools.reference_source import TCC_COLUMNS, TccPayrollAdapter
from tools.reference_step1 import run_reference_step1

def _v4(tmp_path: Path) -> Path:
    """The v4 methodology, made runnable under the year-pack statute seam."""
    return runnable_set("v4", tmp_path)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=TCC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _row(employee: str, unit: str, fein: str, start: str, end: str, pay: str, frequency: str, hours: str, wages: str) -> dict[str, str]:
    return {
        "TCCEmployeeId": employee,
        "Tax Year": "2024",
        "JobTitle": "Analyst",
        "TCCUnitId": unit,
        "PayPeriodStart": start,
        "PayPeriodEnd": end,
        "PaycheckDate": pay,
        "PayFrequency": frequency,
        "FEIN": fein,
        "Hours": hours,
        "Wages": wages,
    }


def _run(tmp_path: Path):
    rows = [
        _row("E1", "U1", "F1", "8/1/2023", "8/31/2023", "8/31/2023", "4", "180", "3000"),
        _row("E1", "U2", "F2", "8/15/2023", "9/30/2023", "9/30/2023", "4", "220", "4000"),
        _row("E2", "U3", "F1", "7/15/2024", "7/21/2024", "7/21/2024", "1", "35", "686"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])
    snapshot = TccPayrollAdapter(source_dir=tmp_path, assumption_path=_v4(tmp_path)).scan()
    return run_reference_onezero(run_reference_step1(snapshot))


def test_onezero_builds_method_specific_grains_and_month12_target(tmp_path: Path):
    result = _run(tmp_path)

    assert result.onezero_assumption_set_id == "GDS-ONEZERO-2026-07-30-v4"
    assert result.onezero_assumption_set_sha256.startswith("sha256:")
    assert result.methodology_workbook_sha256 == "sha256:c2f8cf527af8423f88105d3ee77b30f938d7cfce4e5d532a6c851f60701d310a"
    assert result.historical_wages_pdf_sha256 == "sha256:21a8d16683196f982cbf3040980bec9c8a3a4f2bd1ac686e57647d03185d8208"
    assert result.min_max.months[0].isoformat() == "2023-08-31"
    assert result.min_max.months[-1].isoformat() == "2024-07-31"
    assert len(result.min_max.matrix) == 3
    assert len(result.pay_period.matrix) == 3

    mm_e2 = next(row for row in result.min_max.matrix if row.employee_id == "E2")
    pp_e2 = next(row for row in result.pay_period.matrix if row.employee_id == "E2")
    assert mm_e2.raw_months[-1] == 1
    assert pp_e2.raw_months[-1] == 1
    assert mm_e2.months[-1] == 1
    assert pp_e2.months[-1] == 1


def test_onezero_flags_test_of_twos_and_applies_explicit_tie_break(tmp_path: Path):
    result = _run(tmp_path)

    assert len(result.min_max.overlap_flags) == 1
    assert len(result.pay_period.overlap_flags) == 1
    for method in (result.min_max, result.pay_period):
        flag = method.overlap_flags[0]
        assert flag["employee_id"] == "E1"
        assert flag["month_index"] == 0
        assert "OZ-06" in flag["decision_basis"]
        e1_rows = [row for row in method.matrix if row.employee_id == "E1"]
        assert sum(row.raw_months[0] for row in e1_rows) == 2
        assert sum(row.months[0] for row in e1_rows) == 1
        kept = next(row for row in e1_rows if row.segment_id == flag["kept_segment_id"])
        assert kept.unit_id == "U2"


def test_onezero_summary_exposes_all_precision_views(tmp_path: Path):
    result = _run(tmp_path)

    for method in (result.min_max, result.pay_period):
        u2 = next(row for row in method.summary if row.unit_id == "U2")
        assert u2.month_totals[:2] == [1, 1]
        assert u2.total == 2
        assert u2.included_months == 12
        assert u2.unrounded_average == Decimal(2) / Decimal(12)
        assert u2.source_rounded_average == 0
        assert u2.application_average == Decimal("0.17")

        u3 = next(row for row in method.summary if row.unit_id == "U3")
        assert u3.month_totals[-1] == 1
        assert u3.application_average == Decimal("0.08")


def test_onezero_provenance_and_employee_drill_show_raw_and_disposed_cells(tmp_path: Path):
    result = _run(tmp_path)
    summary = result.summary_dict()

    assert summary["calculation_id"].startswith("sha256:")
    assert [step["step_id"] for step in summary["steps"]] == [
        "GDS.ONEZERO.MIN_MAX.MATRIX",
        "GDS.ONEZERO.PAY_PERIOD.MATRIX",
        "GDS.ONEZERO.SUMMARY",
    ]
    assert all(step["citation"] for step in summary["steps"])
    assert all(step["assumption_ids"] for step in summary["steps"])
    assert summary["min_max"]["monthly_counts_before_disposition"][0] == 2
    assert summary["min_max"]["monthly_counts_after_disposition"][0] == 1

    drill = result.employee_drill("E1")
    assert drill is not None
    assert len(drill["min_max"]) == 2
    assert len(drill["pay_period"]) == 2
    assert len(drill["overlap_flags"]) == 2
    assert result.employee_drill("missing") is None


def test_onezero_is_reproducible_for_same_step1_result(tmp_path: Path):
    rows = [
        _row("E1", "U1", "F1", "8/1/2023", "8/31/2023", "8/31/2023", "4", "180", "3000"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])
    step1 = run_reference_step1(TccPayrollAdapter(source_dir=tmp_path, assumption_path=_v4(tmp_path)).scan())

    first = run_reference_onezero(step1)
    second = run_reference_onezero(step1)

    assert first.calculation_id == second.calculation_id
    assert first.summary_dict() == second.summary_dict()


def test_pay_period_v2_collapses_same_span_matrix_rows(tmp_path: Path):
    rows = [
        _row("E1", "U1", "F1", "8/1/2023", "8/31/2023", "8/31/2023", "4", "90", "1500"),
        _row("E1", "U1", "F1", "8/1/2023", "8/31/2023", "9/1/2023", "4", "90", "1500"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_onezero(run_reference_step1(TccPayrollAdapter(source_dir=tmp_path, assumption_path=_v4(tmp_path)).scan()))

    assert len(result.pay_period.matrix) == 1
    assert result.pay_period.major_period_controls["period_collapse"] == {
        "input_rows": 2,
        "collapsed_period_rows": 1,
        "same_span_rows_collapsed": 1,
        "conflicting_frequency_periods": 0,
    }
    assert result.pay_period.major_period_controls["classification_status"] == "diagnostic_not_signoff_ready"


def test_historical_v1_assumptions_remain_replayable(tmp_path: Path):
    rows = [
        _row("E1", "U1", "F1", "8/1/2023", "8/31/2023", "8/31/2023", "4", "180", "3000"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])
    v1_path = runnable_set("v1", tmp_path)

    step1 = run_reference_step1(
        TccPayrollAdapter(source_dir=tmp_path, assumption_path=v1_path).scan()
    )
    result = run_reference_onezero(step1)

    assert step1.assumption_set_id == "GDS-STEP1-2026-07-29-v1"
    assert result.onezero_assumption_set_id == "GDS-ONEZERO-2026-07-29-v1"
