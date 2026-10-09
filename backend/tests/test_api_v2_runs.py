from __future__ import annotations

import os

import pytest

from tests.certified import (
    CERTIFIED_EMPLOYEES,
    CERTIFIED_MIN_MAX_ELIGIBLE,
    CERTIFIED_PAY_PERIOD_ELIGIBLE,
)


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def lakehouse_source(monkeypatch):
    """The reference client lives in the multi-tenant lakehouse, not the csv demo."""
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")


def test_v2_client_run_round_trips_reference_client(client, lakehouse_source):
    response = client.post(
        "/api/v2/clients/1001/runs",
        json={"year": 2023, "state": "GA"},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["client_id"] == 1001
    assert body["tax_year"] == 2023
    assert body["state"] == "GA"
    assert body["run_status"] == "success"
    assert body["summary"]["employees_evaluated"] == CERTIFIED_EMPLOYEES
    assert body["summary"]["min_max_eligible"] == CERTIFIED_MIN_MAX_ELIGIBLE
    assert body["summary"]["pay_period_eligible"] == CERTIFIED_PAY_PERIOD_ELIGIBLE
    assert body["run_id"]

    latest = client.get("/api/v2/clients/1001/runs/latest")
    assert latest.status_code == 200, latest.text
    latest_body = latest.json()
    assert latest_body["run_id"] == body["run_id"]
    assert latest_body["client_id"] == 1001
    # The manifest carries the run's identity and status, never its figures:
    # those are asserted on the POST body above and read back from Gold.
    assert latest_body["tax_year"] == 2023
    assert latest_body["run_status"] == "success"
    assert "summary" not in latest_body
    assert latest_body["fresh"] in {True, False}
