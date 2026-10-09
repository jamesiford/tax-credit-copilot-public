"""Primary Reference Dataset workspace API and privacy-boundary tests."""
from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from methodology_sources_gate import pytestmark  # noqa: F401
from tools.reference_onezero import run_reference_onezero
from tools.reference_runner import write_private_report
from tools.reference_source import (
    TCC_COLUMNS,
    ReferencePayrollRow,
    TccPayrollAdapter,
    load_assumption_set_for_id,
)
from tools.reference_step1 import run_reference_step1
from tools.reference_workspace import ReferenceWorkspaceService


def _write_source(path: Path) -> None:
    rows = [
        {
            "TCCEmployeeId": "PRIVATE_E1", "Tax Year": "2024", "JobTitle": "A",
            "TCCUnitId": "U1", "PayPeriodStart": "8/1/2023",
            "PayPeriodEnd": "8/31/2023", "PaycheckDate": "8/31/2023",
            "PayFrequency": "4", "FEIN": "F1", "Hours": "180", "Wages": "2880",
        },
        {
            "TCCEmployeeId": "PRIVATE_E2", "Tax Year": "2024", "JobTitle": "B",
            "TCCUnitId": "U2", "PayPeriodStart": "8/1/2023",
            "PayPeriodEnd": "8/7/2023", "PaycheckDate": "8/10/2023",
            "PayFrequency": "1", "FEIN": "F2", "Hours": "10", "Wages": "100",
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


@pytest.fixture
def reference_client(client, tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    service = ReferenceWorkspaceService(source_dir=source, output_dir=tmp_path / "output")
    monkeypatch.setattr("api.workspace._SERVICE", service)
    return client


def test_workspace_summary_is_reference_grounded_and_aggregate_safe(reference_client):
    response = reference_client.get("/api/workspace")
    assert response.status_code == 200
    body = response.json()

    assert body["workspace"] == {
        "id": "reference-dataset-client",
        "name": "Reference Dataset Client",
        # The shell needs these to warn when a sealed view is on screen under a
        # different selection. Both dimensions matter: a year mismatch used to
        # pass silently, which is worse than the client case because nothing on
        # screen looks wrong.
        "account_id": 1001,
        "client_name": "Candle Bottle",
        "tax_year": 2023,
        "program_code": "GA_JTC",
        "single_workspace": True,
        "private_data": True,
    }
    # A sealed run must say which source produced it, and whether that source
    # reproduced the certified figures.
    assert body["run"]["source_kind"] == "csv"
    assert body["equivalence"]["source_kind"] == "csv"
    assert body["source"]["source_kind"] == "csv"
    assert body["eligibility"]["employees_with_totals"] == 2
    assert body["eligibility"]["min_max"]["eligible_employees"] == 1
    assert body["comparison"]["status"] == "not_supplied"
    assert body["stages"][-1]["status"] == "awaiting_outputs"
    assert body["boundary"]["status"] == "MISSING_LEADING_LOOKBACK"
    assert body["boundary"]["synthetic_boundary_rows_added"] == 0
    assert body["boundary"]["force_52_weeks"] is False
    encoded = json.dumps(body)
    assert "PRIVATE_E1" not in encoded
    assert "PRIVATE_E2" not in encoded
    assert "F1" not in encoded


def test_source_and_eligibility_search_are_posted_private_details(reference_client):
    source = reference_client.post("/api/workspace/source/search", json={"q": "PRIVATE_E1"})
    assert source.status_code == 200
    source_body = source.json()
    assert source_body["total"] == 1
    assert source_body["run"]["step1_calculation_id"].startswith("sha256:")
    assert source_body["rows"][0]["employee_id"] == "PRIVATE_E1"
    token = source_body["rows"][0]["record_token"]
    assert "PRIVATE_E1" not in token

    eligibility = reference_client.post(
        "/api/workspace/eligibility/search",
        json={"status": "both", "q": "PRIVATE_E1", "limit": 20, "offset": 0},
    )
    assert eligibility.status_code == 200
    row = eligibility.json()["rows"][0]
    assert row["record_token"] == token
    assert row["min_max"]["eligible"] is True
    assert row["pay_period"]["eligible"] is True
    assert row["near_floor"] is True

    near_floor = reference_client.post(
        "/api/workspace/eligibility/search",
        json={"proximity": "near_floor"},
    )
    assert near_floor.status_code == 200
    assert near_floor.json()["total"] == 1


def test_source_labels_follow_v5_paycheck_date_only_selection():
    assumptions = load_assumption_set_for_id("GDS-STEP1-2026-08-25-v8")["assumptions"]
    row = ReferencePayrollRow(
        source_file="One.csv",
        source_row=2,
        source_tax_year=2023,
        employee_id="PRIVATE_E1",
        job_title="A",
        unit_id="U1",
        pay_period_start=date(2024, 7, 25),
        pay_period_end=date(2024, 8, 6),
        pay_date=date(2024, 8, 1),
        pay_frequency_code="4",
        fein="F1",
        hours=Decimal("40"),
        wages=Decimal("800"),
    )

    assert ReferenceWorkspaceService._selection_reason(row, assumptions) == "included_ppe_after_fy_end"


def test_employee_drill_reaches_source_paycheck_and_both_methods(reference_client):
    rows = reference_client.post("/api/workspace/eligibility/search", json={"q": "PRIVATE_E1"}).json()
    token = rows["rows"][0]["record_token"]
    response = reference_client.post("/api/workspace/employee", json={"record_token": token})
    assert response.status_code == 200
    body = response.json()

    assert body["employee_id"] == "PRIVATE_E1"
    assert body["raw_source_rows"][0]["source_file"] == "One.csv"
    assert body["raw_source_rows"][0]["source_row"] == 2
    assert body["raw_source_rows"][0]["hours"] == "180"
    assert body["raw_source_rows"][0]["wages"] == "2880"
    assert body["step1"]["min_max"]["eligible"] is True
    assert body["step1"]["pay_period"]["eligible"] is True
    assert len(body["onezero"]["min_max"]) == 1
    assert len(body["onezero"]["pay_period"]) == 1


def test_onezero_contributors_and_calculation_walk(reference_client):
    summary = reference_client.get("/api/workspace/onezero/min_max")
    assert summary.status_code == 200
    body = summary.json()
    assert body["assumption_set_id"] == "GDS-ONEZERO-2026-08-24-v7"
    unit = body["summary"][0]

    contributors = reference_client.post(
        "/api/workspace/onezero/contributors",
        json={"method": "min_max", "unit_id": unit["unit_id"], "fein": unit["fein"], "month_index": 0},
    )
    assert contributors.status_code == 200
    assert contributors.json()["contributors"][0]["employee_id"] == "PRIVATE_E1"
    assert contributors.json()["run"]["onezero_calculation_id"].startswith("sha256:")

    walk = reference_client.get("/api/workspace/calculation-walk")
    assert walk.status_code == 200
    walk_body = walk.json()
    assert walk_body["run_context"]["step1_assumption_set_id"] == "GDS-STEP1-2026-08-25-v8"
    assert walk_body["run_context"]["onezero_assumption_set_id"] == "GDS-ONEZERO-2026-08-24-v7"
    assert walk_body["run_context"]["methodology_workbook_sha256"].startswith("sha256:")
    assert walk_body["run_context"]["historical_wages_pdf_sha256"].startswith("sha256:")
    assert len(walk_body["steps"]) == 10
    assert all(step["formula"] for step in walk_body["steps"])
    assert all(step["citation"] for step in walk_body["steps"])
    assert all(step["calculation_id"] for step in walk_body["steps"])
    assert all(step["code_ref"].startswith("tools/reference_") for step in walk_body["steps"])
    assert all(step["source_hash"].startswith("sha256:") for step in walk_body["steps"])
    assert all(step["config_hash"].startswith("sha256:") for step in walk_body["steps"])
    assert all(step["timestamp"] for step in walk_body["steps"])


def test_assumptions_and_access_status_are_honest(reference_client):
    assumptions = reference_client.get("/api/workspace/assumptions")
    assert assumptions.status_code == 200
    body = assumptions.json()
    assert body["step1"]["assumption_set_id"] == "GDS-STEP1-2026-08-25-v8"
    assert body["onezero"]["assumption_set_id"] == "GDS-ONEZERO-2026-08-24-v7"
    assert body["onezero"]["status"] == "stakeholder_confirmed_source_reconciled"
    assert body["history"]["step1"][0]["assumption_set_id"] == "GDS-STEP1-2026-07-29-v1"
    assert body["history"]["step1"][1]["assumption_set_id"] == "GDS-STEP1-2026-07-29-v2"
    assert body["history"]["step1"][2]["assumption_set_id"] == "GDS-STEP1-2026-07-29-v3"
    assert body["history"]["onezero"][0]["assumption_set_id"] == "GDS-ONEZERO-2026-07-29-v1"
    assert body["history"]["onezero"][1]["assumption_set_id"] == "GDS-ONEZERO-2026-07-29-v2"
    assert body["history"]["onezero"][2]["assumption_set_id"] == "GDS-ONEZERO-2026-07-29-v3"
    assert body["run"]["source_manifest_sha256"].startswith("sha256:")


def test_assumptions_expose_statute_separately_from_methodology(reference_client):
    """The floors are on the response, and NOT inside BA-06.

    v8 moved the statutory values into the year pack [ADR-005]. The Rules &
    Assumptions view used to read them out of `BA-06.config`; after the move that
    silently rendered `undefined` rather than failing. This pins the contract the
    UI actually depends on.
    """
    body = reference_client.get("/api/workspace/assumptions").json()

    statutory = body["statutory"]
    assert statutory["program_code"] == "GA_JTC"
    assert statutory["tax_year"] == 2023
    assert statutory["minimum_average_weekly_hours"] == 35.0
    assert statutory["minimum_average_weekly_wages_usd"] == 636.0
    assert statutory["lowest_wage_county"] == "Glascock"
    assert statutory["dol_report_year"] == 2022
    assert statutory["source"] == "rules/ga_jtc/2023.json"
    assert statutory["prototype_verify"] is False

    ba06 = body["step1"]["assumptions"]["BA-06"]["config"]
    for moved in (
        "minimum_average_weekly_hours",
        "minimum_average_weekly_wages_usd",
        "source_tax_year",
        "dol_report_year",
        "lowest_wage_county",
    ):
        assert moved not in ba06, f"{moved} is statute and must not be back in BA-06"

    comparison = reference_client.get("/api/workspace/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["status"] == "not_supplied"
    assert comparison.json()["run"]["step1_calculation_id"].startswith("sha256:")
    stage = reference_client.post(
        "/api/workspace/comparison/stage",
        json={"stage": "common_employee_totals"},
    )
    assert stage.status_code == 404


def test_remote_requests_are_rejected_before_data_load():
    from api.workspace import _require_local

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("203.0.113.10", 1234)})
    with pytest.raises(HTTPException) as exc:
        _require_local(request)
    assert exc.value.status_code == 403


def test_access_difference_uses_opaque_employee_drill_token(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    snapshot = TccPayrollAdapter(source_dir=source).scan()
    step1 = run_reference_step1(snapshot)
    onezero = run_reference_onezero(step1)
    bundle = tmp_path / "access"
    write_private_report(step1, onezero, snapshot.manifest_dict(), bundle)

    totals_path = bundle / "common_employee_totals.csv"
    rows = list(csv.DictReader(totals_path.open(newline="", encoding="utf-8")))
    rows[0]["TotalHours"] = "179"
    with totals_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    service = ReferenceWorkspaceService(
        source_dir=source,
        output_dir=tmp_path / "output",
        access_output_path=bundle,
    )
    stage = service.comparison_stage("common_employee_totals")

    assert stage is not None
    difference = stage["differences"][0]
    assert difference["key"] == ["PRIVATE_E1"]
    assert difference["record_token"]
    assert "PRIVATE_E1" not in difference["record_token"]
    assert service.comparison_summary(service.get())["source"] == "access"
