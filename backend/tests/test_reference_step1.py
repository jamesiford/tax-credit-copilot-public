"""Reference Dataset Step 1 eligibility and provenance tests."""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from assumption_variants import runnable_set
from tools.reference_source import TCC_COLUMNS, TccPayrollAdapter
from tools.reference_step1 import run_reference_step1


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=TCC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _row(employee: str, start: str, end: str, pay: str, hours: str, wages: str, **overrides: str) -> dict[str, str]:
    row = {
        "TCCEmployeeId": employee,
        "Tax Year": "2024",
        "JobTitle": "Analyst",
        "TCCUnitId": "U1",
        "PayPeriodStart": start,
        "PayPeriodEnd": end,
        "PaycheckDate": pay,
        "PayFrequency": "1",
        "FEIN": "F1",
        "Hours": hours,
        "Wages": wages,
    }
    row.update(overrides)
    return row


def _docs_data() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "data"


def _snapshot(tmp_path: Path, assumption_version: str = "v4"):
    rows = [
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "40", "700"),
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "-5", "-50"),
        _row("E1", "8/8/2023", "8/14/2023", "8/17/2023", "40", "700"),
        _row("E1", "8/8/2023", "8/14/2023", "8/18/2023", "0", "100"),
        _row("E2", "8/1/2023", "8/31/2023", "8/31/2023", "100", "3000", PayFrequency="4"),
        _row("E3", "9/1/2023", "9/7/2023", "9/8/2023", "35", "685.995"),
        _row("E4", "7/25/2024", "7/31/2024", "8/9/2024", "40", "800"),
        _row("E5", "7/25/2023", "8/1/2023", "8/3/2023", "80", "1400", PayFrequency="2"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])
    return TccPayrollAdapter(
        source_dir=tmp_path,
        assumption_path=runnable_set(assumption_version, tmp_path),
    ).scan()


def test_step1_applies_fiscal_selection_and_signed_collapse(tmp_path: Path):
    result = run_reference_step1(_snapshot(tmp_path))

    assert result.selection_counts["input"] == 8
    assert result.selection_counts["included"] == 7
    assert result.selection_counts["excluded_pay_date_after_fy"] == 1
    assert result.selection_counts["included_transcends_fy_start"] == 1
    assert result.collapse_counts == {
        "input_rows": 7,
        "collapsed_rows": 6,
        "duplicate_rows_collapsed": 1,
        "multi_line_groups": 1,
    }
    assert "E4" not in result.common_totals
    assert result.common_totals["E1"].total_hours == Decimal("75")
    assert result.common_totals["E1"].total_wages == Decimal("1450")


def test_step1_computes_both_denominators_and_eligibility(tmp_path: Path):
    result = run_reference_step1(_snapshot(tmp_path))

    min_max = result.min_max["E1"]
    pay_period = result.pay_period["E1"]
    assert min_max.denominator_weeks == Decimal("2")
    assert min_max.denominator_detail["inclusive_days"] == 14
    assert pay_period.denominator_weeks == Decimal("2")
    assert pay_period.denominator_detail["included_period_count"] == 2
    assert pay_period.denominator_detail["cadence_counts"] == {"1": 2}
    assert min_max.rounded_avg_weekly_hours == Decimal("37.50")
    assert min_max.rounded_avg_weekly_wages == Decimal("725.00")
    assert min_max.eligible is True
    assert pay_period.eligible is True

    assert result.min_max["E2"].eligible is False
    assert result.pay_period["E2"].denominator_weeks == Decimal("4.333")
    assert result.pay_period["E2"].eligible is False

    # BA-06 v4 tests the two-decimal rounded value: 685.995 -> 686.00.
    assert result.min_max["E3"].rounded_avg_weekly_wages == Decimal("686.00")
    assert result.min_max["E3"].eligible is True
    assert result.pay_period["E3"].eligible is True

    assert result.min_max["E5"].denominator_detail["first_start"] == "2023-07-25"
    assert result.pay_period["E5"].denominator_weeks == Decimal("2.0")


def test_step1_summary_and_employee_drill_show_work(tmp_path: Path):
    result = run_reference_step1(_snapshot(tmp_path))
    summary = result.summary_dict()

    assert summary["assumption_set_id"] == "GDS-STEP1-2026-07-30-v4"
    assert summary["source_manifest_sha256"].startswith("sha256:")
    assert summary["calculation_id"].startswith("sha256:")
    assert summary["min_max"]["eligible_employees"] == 3
    assert summary["pay_period"]["eligible_employees"] == 3
    assert summary["eligibility_reconciliation"] == {
        "eligible_both": 3,
        "min_max_only": 0,
        "pay_period_only": 0,
    }
    assert [step["step_id"] for step in summary["steps"]] == [
        "GDS.SOURCE.SELECT",
        "GDS.SOURCE.BOUNDARY_COMPLETENESS",
        "GDS.SOURCE.COLLAPSE",
        "GDS.EMPLOYEE.TOTALS",
        "GDS.ELIGIBILITY.MIN_MAX",
        "GDS.ELIGIBILITY.PAY_PERIOD",
        "GDS.ELIGIBILITY.RECONCILE",
    ]
    assert all(step["citation"] for step in summary["steps"])
    assert all(step["formula"] for step in summary["steps"])

    drill = result.employee_drill("E1")
    assert drill is not None
    assert drill["totals"] == {"total_hours": "75", "total_wages": "1450"}
    assert len(drill["source_rows"]) == 3
    assert drill["source_rows"][0]["source_refs"] == [["One.csv", 2], ["One.csv", 3]]
    assert drill["min_max"]["eligible"] is True
    assert drill["pay_period"]["eligible"] is True
    assert result.employee_drill("missing") is None


def _adapter(tmp_path: Path, assumption_version: str = "v4") -> TccPayrollAdapter:
    return TccPayrollAdapter(
        source_dir=tmp_path,
        assumption_path=runnable_set(assumption_version, tmp_path),
    )


def test_pay_period_v2_collapses_same_pps_ppe_and_preserves_lineage(tmp_path: Path):
    rows = [
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "20", "350"),
        _row("E1", "8/1/2023", "8/7/2023", "8/11/2023", "20", "350"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path).scan())
    detail = result.pay_period["E1"].denominator_detail

    assert result.pay_period["E1"].denominator_weeks == Decimal("1.0")
    assert detail["source_period_key_count"] == 2
    assert detail["collapsed_period_count"] == 1
    assert detail["same_pps_ppe_records_collapsed"] == 1
    assert detail["period_keys"][0]["pay_dates"] == ["2023-08-10", "2023-08-11"]


def test_pay_period_v2_flags_conflicting_cadence_without_repair(tmp_path: Path):
    rows = [
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "20", "350"),
        _row(
            "E1", "8/1/2023", "8/7/2023", "8/11/2023", "20", "350",
            PayFrequency="2",
        ),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path).scan())
    detail = result.pay_period["E1"].denominator_detail

    assert result.pay_period["E1"].denominator_weeks == Decimal("0")
    assert detail["conflicting_frequency_periods"] == [{
        "pay_period_start": "2023-08-01",
        "pay_period_end": "2023-08-07",
        "frequency_codes": ["1", "2"],
    }]
    assert result.pay_period_controls()["conflicting_frequency_periods"] == 1


def test_step1_v2_reports_invariant_without_capping(tmp_path: Path):
    rows = [
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "40", "700", PayFrequency="4"),
        _row("E1", "8/8/2023", "8/14/2023", "8/17/2023", "40", "700", PayFrequency="4"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path).scan())
    control = result.denominator_invariant()

    assert result.pay_period["E1"].denominator_weeks == Decimal("8.666")
    assert result.min_max["E1"].denominator_weeks == Decimal("2")
    assert control["pay_period_gt_min_max"] == 1
    assert control["pay_period_gt_min_max_over_review_tolerance"] == 1
    assert control["repair_policy"] == "none"


def test_step1_run_is_reproducible_for_same_source_and_config(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    first = run_reference_step1(snapshot)
    second = run_reference_step1(snapshot)

    assert first.calculation_id == second.calculation_id
    assert first.source_manifest_sha256 == second.source_manifest_sha256
    assert first.summary_dict() == second.summary_dict()


def test_v4_includes_prior_ppe_paid_in_fy_and_preserves_crossing_period(tmp_path: Path):
    rows = [
        _row("E1", "7/15/2023", "7/21/2023", "8/3/2023", "40", "700"),
        _row("E1", "7/22/2023", "8/4/2023", "8/10/2023", "40", "700"),
        _row("E1", "8/5/2023", "8/11/2023", "8/17/2023", "40", "700"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path).scan())

    assert result.selection_counts["included"] == 3
    assert result.selection_counts["included_prior_ppe_paid_in_fy"] == 1
    assert result.selection_counts["included_transcends_fy_start"] == 1
    assert result.pay_period["E1"].denominator_weeks == Decimal("3.0")
    assert result.boundary_controls["status"] == "LEADING_LOOKBACK_PRESENT"
    assert result.boundary_controls["prior_ppe_paid_in_fy_rows"] == 1
    assert result.boundary_controls["crossing_start_rows"] == 1
    assert result.boundary_controls["synthetic_boundary_rows_added"] == 0


def test_v3_replay_excludes_prior_ppe_paid_in_fy(tmp_path: Path):
    rows = [
        _row("E1", "7/15/2023", "7/21/2023", "8/3/2023", "40", "700"),
        _row("E1", "7/22/2023", "8/4/2023", "8/10/2023", "40", "700"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])
    v3_path = runnable_set("v3", tmp_path)

    result = run_reference_step1(
        TccPayrollAdapter(source_dir=tmp_path, assumption_path=v3_path).scan()
    )

    assert result.assumption_set_id == "GDS-STEP1-2026-07-29-v3"
    assert result.selection_counts["included"] == 1
    assert result.selection_counts["excluded_ppe_before_fy"] == 1


def test_v4_reports_missing_leading_lookback_without_forcing_weeks(tmp_path: Path):
    _write(
        tmp_path / "One.csv",
        [_row("E1", "8/5/2023", "8/11/2023", "8/17/2023", "40", "700")],
    )
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path).scan())

    assert result.boundary_controls["status"] == "MISSING_LEADING_LOOKBACK"
    assert result.boundary_controls["boundary_complete"] is False
    assert result.boundary_controls["force_52_weeks"] is False
    assert result.min_max["E1"].denominator_weeks == Decimal("1")
    assert any("not forced to 52" in exception for exception in result.exceptions)


def test_v6_short_pay_periods_are_excluded_from_numerator_and_span(tmp_path: Path):
    """BA-12. The partner removes 1-6 day pay periods before analysis.

    The trailing one-day period would otherwise stretch the Min-Max span and add
    its wages to the numerator. Under v6 both effects disappear.
    """
    rows = [
        _row("E1", "8/1/2023", "8/15/2023", "8/15/2023", "81.25", "1852.83"),
        _row("E1", "9/15/2023", "9/15/2023", "9/15/2023", "0", "250"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    v5 = run_reference_step1(_adapter(tmp_path, "v5").scan())
    v6 = run_reference_step1(_adapter(tmp_path, "v6").scan())

    # v5 keeps the one-day period: span runs to 15 September and wages include $250.
    assert v5.common_totals["E1"].total_wages == Decimal("2102.83")
    assert v5.min_max["E1"].denominator_detail["last_end"] == "2023-09-15"

    # v6 drops it from both.
    assert v6.common_totals["E1"].total_wages == Decimal("1852.83")
    assert v6.min_max["E1"].denominator_detail["last_end"] == "2023-08-15"
    assert v6.min_max["E1"].denominator_detail["minimum_pay_period_days"] == 7


def test_v6_employee_with_only_short_periods_drops_out(tmp_path: Path):
    """The partner: two employees fell out of their population entirely for this reason."""
    rows = [_row("E1", "8/1/2023", "8/4/2023", "8/4/2023", "40", "3000")]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v6").scan())

    assert "E1" not in result.common_totals
    assert result.min_max["E1"].denominator_weeks == Decimal("0") if "E1" in result.min_max else True


def test_v5_replays_without_the_short_period_rule(tmp_path: Path):
    """Superseded sets must keep reproducing their original numbers."""
    rows = [
        _row("E1", "8/1/2023", "8/15/2023", "8/15/2023", "81.25", "1852.83"),
        _row("E1", "9/15/2023", "9/15/2023", "9/15/2023", "0", "250"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v5").scan())

    assert result.assumption_set_id == "GDS-STEP1-2026-08-05-v5"
    assert result.min_max["E1"].denominator_detail["minimum_pay_period_days"] == 0


def test_v7_keeps_short_period_wages_in_the_numerator(tmp_path: Path):
    """BA-12 v7. The partner's 2026-08-20 correction to their own reconciliation.

    The one-day period is excluded from the span but its $250 stays in the
    numerator: "I go back to the stored payroll file where I aggregated all
    wages paid, all hours worked, irrespective of good or bad pay periods."
    v6 removed it from both, reproducing the error they identified on their side.
    """
    rows = [
        _row("E1", "8/1/2023", "8/15/2023", "8/15/2023", "81.25", "1852.83"),
        _row("E1", "9/15/2023", "9/15/2023", "9/15/2023", "0", "250"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    v6 = run_reference_step1(_adapter(tmp_path, "v6").scan())
    v7 = run_reference_step1(_adapter(tmp_path, "v7").scan())

    # v6 chopped the numerator too — the error the partner flagged.
    assert v6.common_totals["E1"].total_wages == Decimal("1852.83")

    # v7 keeps every dollar, while both still exclude the period from the span.
    assert v7.common_totals["E1"].total_wages == Decimal("2102.83")
    assert v7.min_max["E1"].denominator_detail["last_end"] == "2023-08-15"
    assert v6.min_max["E1"].denominator_detail["last_end"] == "2023-08-15"


def test_v7_reports_short_period_exclusions_for_review(tmp_path: Path):
    """Exclusions are a soft delete, not a silent drop.

    The partner asked for this directly: "capture the ineligibles and then give the
    user the ability to review... we should have some sort of exception report."
    """
    rows = [
        _row("E1", "8/1/2023", "8/15/2023", "8/15/2023", "81.25", "1852.83"),
        _row("E1", "9/15/2023", "9/15/2023", "9/15/2023", "0", "250"),
        _row("E2", "8/1/2023", "8/4/2023", "8/4/2023", "40", "3000"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    report = run_reference_step1(_adapter(tmp_path, "v7").scan()).short_period_exclusions

    assert report["minimum_pay_period_days"] == 7
    assert report["excluded_rows"] == 2
    assert report["excluded_rows_by_period_length"] == {1: 1, 4: 1}
    assert report["excluded_wages"] == "3250"
    assert report["employees_touched"] == 2
    # E2 has nothing left; E1 still has a valid period.
    assert report["employees_left_with_no_valid_period"] == 1
    assert report["numerator_treatment"] == "retained"
    assert report["disposition"] == "soft_delete_reviewable"


def test_v8_is_the_active_default_assumption_set(tmp_path: Path):
    _write(tmp_path / "One.csv", [_row("E1", "8/5/2023", "8/11/2023", "8/17/2023", "40", "700")])
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    snapshot = TccPayrollAdapter(source_dir=tmp_path).scan()

    assert snapshot.assumption_set_id == "GDS-STEP1-2026-08-25-v8"


def test_retired_assumption_sets_refuse_to_run(tmp_path: Path):
    """A superseded set must fail loudly, not resolve someone else's statute.

    v1-v7 hold their wage floor inline in BA-06 and name no tax year. Running one
    unchanged would mean silently applying whichever floor the engine reached for
    — the exact failure ADR-005 exists to prevent.
    """
    import pytest

    from tools.reference_source import RETIRED_ASSUMPTION_SETS, load_assumption_set_for_id

    assert "GDS-STEP1-2026-08-24-v7" in RETIRED_ASSUMPTION_SETS
    for retired in RETIRED_ASSUMPTION_SETS:
        with pytest.raises(ValueError, match="retired"):
            load_assumption_set_for_id(retired)


def test_v5_keeps_rows_whose_period_ends_after_fiscal_year_end(tmp_path: Path):
    """The partner trims on paycheck date only; a period ending past FY end still counts."""
    rows = [
        _row("E1", "7/25/2024", "8/6/2024", "8/1/2024", "40", "800"),
        _row("E1", "7/18/2024", "7/24/2024", "8/9/2024", "40", "800"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v5").scan())

    assert result.selection_counts["included"] == 1
    assert result.selection_counts["included_ppe_after_fy_end"] == 1
    assert result.selection_counts["excluded_pay_date_after_fy"] == 1
    assert "excluded_ppe_after_fy" not in result.selection_counts


def test_v5_pay_period_denominator_uses_actual_span_not_frequency_code(tmp_path: Path):
    """PayFrequency 4 spans the 16th-31st (16 days), not four weeks."""
    rows = [
        _row("E1", "8/16/2023", "8/31/2023", "8/31/2023", "80", "1600", PayFrequency="4"),
        _row("E1", "9/1/2023", "9/15/2023", "9/15/2023", "80", "1600", PayFrequency="2"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v5").scan())
    detail = result.pay_period["E1"].denominator_detail

    # (16 days + 15 days) / 7 rather than the literal 4 + 2 = 6 weeks.
    assert result.pay_period["E1"].denominator_weeks == Decimal("31") / Decimal("7")
    assert detail["denominator_mode"] == "actual_span_inclusive"


def test_v5_retains_zero_hour_periods_in_the_denominator(tmp_path: Path):
    rows = [
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "40", "700"),
        _row("E1", "8/8/2023", "8/14/2023", "8/17/2023", "0", "100"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v5").scan())
    detail = result.pay_period["E1"].denominator_detail

    assert detail["counts_zero_hour_periods"] is True
    assert detail["included_period_count"] == 2
    assert result.pay_period["E1"].denominator_weeks == Decimal("2")


def test_v5_min_max_span_is_exclusive_and_spans_zero_hour_rows(tmp_path: Path):
    """One Zero Min Max.docx Step 2: days between FirstStart and LastEnd, divided by 7."""
    rows = [
        _row("E1", "8/1/2023", "8/7/2023", "8/10/2023", "40", "700"),
        _row("E1", "8/8/2023", "8/15/2023", "8/17/2023", "0", "0"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v5").scan())
    detail = result.min_max["E1"].denominator_detail

    assert detail["span_mode"] == "exclusive_days"
    assert detail["excludes_zero_hour_rows"] is False
    assert detail["first_start"] == "2023-08-01"
    assert detail["last_end"] == "2023-08-15"
    assert result.min_max["E1"].denominator_weeks == Decimal("14") / Decimal("7")


def test_v5_applies_the_tax_year_2023_wage_floor(tmp_path: Path):
    """TY2023 = $636/wk (DOL 2022, Glascock). $635.99 must fail, $636.00 must pass."""
    rows = [
        _row("BELOW", "8/1/2023", "8/7/2023", "8/10/2023", "40", "635.99"),
        _row("AT", "8/1/2023", "8/7/2023", "8/10/2023", "40", "636.00"),
    ]
    _write(tmp_path / "One.csv", rows)
    for name in ("Two.csv", "Three.csv", "Four.csv"):
        _write(tmp_path / name, [])

    result = run_reference_step1(_adapter(tmp_path, "v5").scan())

    assert result.pay_period["BELOW"].eligible is False
    assert result.pay_period["AT"].eligible is True
