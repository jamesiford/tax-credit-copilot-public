"""Tests for the Fabric Lakehouse source mapper + adapter (ROADMAP-V · F2/F3).

The mapper is pure and validated against the REAL Fabric `employees` schema
(from the `partner_tax_credit_demo_lakehouse` sample). The adapter's live
SQL-endpoint read is not exercised (no live Fabric); we test that it degrades
to `[]` when not configured and reports `is_configured()` correctly.
"""
from __future__ import annotations

from datetime import date

import pytest

from tools import fabric_source as fs
from tools.canonical import to_canonical


# A real-shape Fabric `employees` row (from the Lakehouse sample).
_FABRIC_ROW = {
    "Social_Security_Number": "621-48-2965",
    "Employee_ID": "E100001",
    "First_Name": "Angela",
    "Last_Name": "Wright",
    "Hire_Date": "12/15/2017",
    "Job_Title": "Recruiter",
    "Location_ID": "IN001",
    "FEIN": "572822765",
    "Worksite_ID": "WS069",
    "Work_State": "NC",
    "Pay_Period_Start": "8/10/2026",
    "Pay_Period_End": "8/23/2026",
    "Check_Date": "8/28/2026",
    "Pay_Frequency": "Weekly",
    "Hours": "37.55",
    "Gross_Wages": "$1,306.74 ",
    "Earning_Code": "Regular",
    "Employment_Type": "Full-Time",
}


def test_parse_money_strips_currency():
    assert fs._parse_money("$1,306.74 ") == 1306.74
    assert fs._parse_money("$960.59 ") == 960.59
    assert fs._parse_money("92.28") == 92.28
    assert fs._parse_money("") == 0.0
    assert fs._parse_money(1500) == 1500.0


def test_parse_date_handles_us_and_iso():
    assert fs._parse_date("8/10/2026") == "2026-08-10"
    assert fs._parse_date("12/15/2017") == "2017-12-15"
    assert fs._parse_date("2026-08-10") == "2026-08-10"
    assert fs._parse_date("") == ""


def test_map_fabric_row_to_prototype_shape():
    row = fs.map_fabric_employees_row(_FABRIC_ROW)
    # State-prefixed worksite so the existing per-state filtering keeps working.
    assert row["Worksite_ID"] == "NC_WS069"
    assert row["Work_State"] == "NC"
    assert row["Location_ID"] == "IN001"
    # Tax year derived from the paycheck (Check_Date) year — cash-basis (DATA-06).
    assert row["Tax_Year"] == 2026
    assert row["Pay_Period_Start"] == "2026-08-10"
    assert row["Pay_Period_End"] == "2026-08-23"
    assert row["Pay_Date"] == "2026-08-28"
    assert row["Entity_FEIN"] == "572822765"
    assert row["Hours_Worked"] == 37.55
    assert row["Gross_Wages"] == 1306.74
    assert row["Pay_Code"] == "Regular"
    assert row["Employee_ID"] == "E100001"
    assert row["Job_Title"] == "Recruiter"


def test_mapped_row_flows_through_to_canonical():
    """A mapped Fabric row is consumable by the canonical pipeline unchanged."""
    mapped = fs.map_fabric_employees_row(_FABRIC_ROW)

    class _StaticAdapter:
        def rows(self):
            return [mapped]

    records = to_canonical(_StaticAdapter(), tax_year=2026)
    assert len(records) == 1
    rec = records[0]
    assert rec.employee_id == "E100001"
    assert rec.worksite_id == "NC_WS069"
    assert rec.hours_worked == 37.55
    assert rec.gross_wages == 1306.74
    assert rec.includable is True  # Regular is includable


def test_adapter_degrades_when_not_configured(monkeypatch):
    """With nothing set the product reads Fabric, not a local file.

    The default was `csv`, which meant a misconfigured deployment answered from
    a synthetic single-tenant file instead of failing. `csv` is now a test
    fixture that `conftest.py` selects explicitly; nothing that ships picks it.
    """
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    monkeypatch.delenv("FABRIC_WORKSPACE", raising=False)
    assert fs.active_data_source() == "lakehouse"
    adapter = fs.FabricEmployeesAdapter()
    assert adapter.is_configured() is False
    assert list(adapter.rows()) == []


def test_the_csv_fixture_is_still_selectable_for_the_offline_suite(monkeypatch):
    """It has to remain reachable, or the suite cannot run without Fabric."""
    monkeypatch.setenv("DATA_SOURCE", "csv")
    assert fs.active_data_source() == "csv"


def test_flex_is_a_deprecated_alias_for_lakehouse(monkeypatch):
    """The source schema used to be named after the customer's internal shape.

    `DATA_SOURCE=flex` must keep resolving to exactly what `lakehouse` resolves
    to, and must say so with a `DeprecationWarning` rather than silently
    diverging — this is the one place that alias is allowed to appear outside
    the implementation itself.
    """
    monkeypatch.setenv("DATA_SOURCE", "flex")
    with pytest.warns(DeprecationWarning, match="DATA_SOURCE=flex is deprecated"):
        resolved = fs.active_data_source()
    assert resolved == "lakehouse"

    monkeypatch.setenv("DATA_SOURCE", "FLEX")
    with pytest.warns(DeprecationWarning):
        assert fs.active_data_source() == "lakehouse"


def test_adapter_configured_flag(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "fabric")
    monkeypatch.setenv("FABRIC_WORKSPACE", "partner-tax-credit-demo")
    monkeypatch.setenv("FABRIC_LAKEHOUSE", "partner_tax_credit_demo_lakehouse")
    adapter = fs.FabricEmployeesAdapter()
    # Configured — but we do NOT call rows() (that would hit the live endpoint).
    assert adapter.is_configured() is True
    assert adapter.qualified_table() == (
        "[partner_tax_credit_demo_lakehouse].[dbo].[employees]"
    )


def test_the_lakehouse_is_reached_by_three_part_name_not_a_storage_uri():
    """The point of the T-SQL read: this follows the partner to SQL Server.

    A three-part name is a connection-string change away from any SQL Server; an
    `abfss://` URI is a rewrite. Asserted so a revert to storage is visible.
    """
    adapter = fs.FabricEmployeesAdapter(
        lakehouse="lh", employees_table="dbo/employees"
    )
    qualified = adapter.qualified_table()

    assert qualified == "[lh].[dbo].[employees]"
    assert "abfss" not in qualified and "onelake" not in qualified.lower()
    assert not hasattr(adapter, "table_uri")


def test_a_table_name_cannot_break_out_of_its_brackets():
    """Identifiers come from configuration, so they are quoted, not concatenated."""
    adapter = fs.FabricEmployeesAdapter(
        lakehouse="lh", employees_table="dbo/employees]; DROP TABLE x--"
    )
    assert adapter.qualified_table() == "[lh].[dbo].[employees]]; DROP TABLE x--]"


def test_a_table_without_a_schema_defaults_to_dbo():
    adapter = fs.FabricEmployeesAdapter(lakehouse="lh", employees_table="employees")
    assert adapter.qualified_table() == "[lh].[dbo].[employees]"


def test_fabric_csv_seed_round_trips_to_pay_periods(tmp_path):
    """POC-02 reconciliation: the Fabric-shaped seed Employees.csv reconstructs
    the EXACT pay-period facts when read back through the mapper — 'shape is the
    Fabric shape, data is the same MeridianCore data'. Row-for-row multiset.

    NOTE: `Tax_Year` is intentionally excluded — the prototype CSV carries an
    explicit `Tax_Year` column, but the Fabric shape has none and the engine
    derives the fiscal year from `Pay_Date` (cash-basis; `onezero.preprocess`
    filters on `fiscal_year_of(Pay_Date)`), which round-trips exactly. So the
    informational column differs on boundary rows while every computed number
    holds (proven by `test_fabric_seed_reconciles_ga_average_headcount`)."""
    import csv
    from collections import Counter
    from pathlib import Path
    from data.generate_fabric_employees import build

    # Into tmp_path at a fixed date: a test must never rewrite the tracked seed.
    build(out_dir=tmp_path, as_of=date(2026, 1, 1))

    def _key(r: dict) -> tuple:
        return (
            r["Employee_ID"], r["Worksite_ID"], r["Pay_Period_Start"], r["Pay_Period_End"],
            r["Pay_Date"], r["Pay_Code"], r["Entity_FEIN"],
            round(float(r["Hours_Worked"]), 2), round(float(r["Gross_Wages"]), 2),
        )

    pp_path = Path(__file__).resolve().parent.parent / "data" / "payroll_pay_periods.csv"
    with pp_path.open(newline="", encoding="utf-8") as f:
        baseline = Counter(_key(r) for r in csv.DictReader(f))

    mapped = Counter(_key(m) for m in fs.FabricCsvAdapter(path=tmp_path / "Employees.csv").rows())
    assert mapped == baseline


def test_fabric_seed_reconciles_ga_average_headcount(tmp_path):
    """Definitive 'numbers hold': the GA 2025 Average Headcount computed from the
    Fabric-shaped seed equals the value computed from the CSV baseline — the
    engine reads the same facts regardless of source shape."""
    import csv
    from datetime import date
    from pathlib import Path
    from data.generate_fabric_employees import build
    from tools.credit_math import load_pack_one_zero
    from domain.calculation.onezero import run_pay_period_method, fiscal_window_start, fiscal_year_of

    build(out_dir=tmp_path, as_of=date(2026, 1, 1))
    pack = load_pack_one_zero("GA", tax_year=2025)
    start = fiscal_window_start(2025, 12)

    def ga_avg(rows: list[dict]) -> float:
        ga = [
            r for r in rows
            if str(r["Worksite_ID"]).startswith("GA_")
            and fiscal_year_of(date.fromisoformat(str(r["Pay_Date"])[:10])) == 2025
        ]
        return run_pay_period_method(ga, tax_year=2025, analysis_start_month=start, pack=pack).annual_average

    pp_path = Path(__file__).resolve().parent.parent / "data" / "payroll_pay_periods.csv"
    with pp_path.open(newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    fabric_rows = list(fs.FabricCsvAdapter(path=tmp_path / "Employees.csv").rows())

    assert ga_avg(csv_rows) == ga_avg(fabric_rows) > 0
