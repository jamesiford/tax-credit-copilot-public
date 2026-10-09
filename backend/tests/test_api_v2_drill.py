"""The v2 drill, against `tcc_gold`.

These read the warehouse, so they need a client that has actually been
calculated. Cascade (2001) is the fixture: six priceable years, so it exercises
the credit layer including tranches, which the single-year reference client
cannot.
"""
from __future__ import annotations

import os

import pytest


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def warehouse():
    """The v2 reads take their figures from Gold, not from a payroll source."""
    _requires_fabric()


def test_v2_client_units_surfaces_the_whole_credit_layer(warehouse, client):
    response = client.get("/api/v2/clients/2001/units?year=2023&method=min_max&limit=50")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["calculation_state"] == "calculated"
    assert body["run"]["produced_at"], "a figure must carry when it was produced"
    assert body["total"] >= 1
    assert body["method"] == "min_max"

    first = body["items"][0]
    for column in (
        "worksite_id", "tax_year", "program_code", "method", "average_headcount",
        "eligible_jobs", "new_jobs_created", "high_water_mark", "net_new_vs_base",
        "per_job_usd", "tranche_years", "annual_credit_usd", "is_current", "run_id",
    ):
        assert column in first, column

    # The dollar is checkable from the row that carries it. That is the reason
    # per_job_usd is in Gold at all.
    from decimal import Decimal

    for item in body["items"]:
        if item["eligible_jobs"] is None or item["per_job_usd"] is None:
            continue
        expected = round(Decimal(str(item["eligible_jobs"])) * Decimal(item["per_job_usd"]))
        assert abs(Decimal(item["annual_credit_usd"]) - expected) <= 1, item["worksite_id"]


def test_v2_client_units_reports_new_jobs_created_rather_than_dropping_it(warehouse, client):
    """Cascade falls below its frozen base and recovers across six years.

    Asserting only `eligible_jobs != new_jobs_created` is not enough — that
    passes trivially when `new_jobs_created` is hardcoded to 0.0, which is
    exactly the bug an earlier version of this test failed to catch.
    """
    body = client.get("/api/v2/clients/2001/units?method=min_max&limit=200").json()
    assert body["calculation_state"] == "calculated"

    values = [
        item["new_jobs_created"] for item in body["items"]
        if item["new_jobs_created"] is not None
    ]
    assert values, "no new_jobs_created values at all"
    assert any(value > 0 for value in values), (
        "new_jobs_created is zero in every row — it is being dropped between "
        "tools/baseyear.py and the warehouse rather than computed"
    )


def test_v2_unit_drill_narrows_to_the_month_rather_than_annotating_it(warehouse, client):
    listing = client.get("/api/v2/clients/2001/units?year=2023&method=min_max&limit=50").json()
    worksite = listing["items"][0]["worksite_id"]

    whole_year = client.get(
        f"/api/v2/clients/2001/units/{worksite}?year=2023&method=min_max"
    ).json()
    month_five = client.get(
        f"/api/v2/clients/2001/units/{worksite}?year=2023&month=5&method=min_max"
    ).json()

    assert whole_year["unit"]["worksite_id"] == worksite
    assert month_five["month_filter"]["month_index"] == 5
    assert month_five["employees"], "month 5 has contributors"

    # Narrowed, not annotated: everyone returned for a month contributed to it,
    # and the count reflects that.
    assert month_five["total"] == len(month_five["employees"])
    assert all(employee["month_05"] > 0 for employee in month_five["employees"])
    assert month_five["total"] <= whole_year["total"]


def test_v2_employee_endpoint_resolves_the_record_token_from_gold(warehouse, client):
    listing = client.get("/api/v2/clients/2001/units?year=2023&method=min_max&limit=50").json()
    worksite = listing["items"][0]["worksite_id"]
    drill = client.get(
        f"/api/v2/clients/2001/units/{worksite}?year=2023&method=min_max"
    ).json()
    token = drill["employees"][0]["record_token"]

    response = client.get(f"/api/v2/employees/{token}?client_id=2001&year=2023")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["calculation_state"] == "calculated"
    assert body["record_token"] == token
    assert body["eligibility"], "an employee in the matrix has an eligibility row"
    assert {row["method"] for row in body["eligibility"]} == {"min_max", "pay_period"}
    assert body["units"], "and at least one unit allocation"


def test_a_token_from_another_client_does_not_resolve(warehouse, client):
    """Tenant isolation on the drill key, read from the warehouse."""
    listing = client.get("/api/v2/clients/2001/units?year=2023&method=min_max&limit=50").json()
    worksite = listing["items"][0]["worksite_id"]
    drill = client.get(
        f"/api/v2/clients/2001/units/{worksite}?year=2023&method=min_max"
    ).json()
    token = drill["employees"][0]["record_token"]

    response = client.get(f"/api/v2/employees/{token}?client_id=1001&year=2023")
    assert response.status_code == 404
