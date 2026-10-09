"""A tax year is a fiscal window, not the calendar year of the same name.

The scope selector offered Candle Bottle "TY2023 · 5mo" and "TY2024 · 8mo" —
two partial years — because it bucketed pay dates by calendar year. The client
has ONE complete tax year: a 53-week fiscal calendar running 2023-07-28 to
2024-08-02, which the Georgia regulation labels by the year it begins.

These are live-Fabric tests because per-client fiscal rules only exist in the
lakehouse source. Under `csv` the window is a flagged calendar assumption, and
the calendar and the fiscal year agree by construction — so the bug is
invisible there, which is exactly why it survived.
"""
from __future__ import annotations

import os

import pytest


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def lakehouse_client(monkeypatch):
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


def test_a_non_calendar_filer_gets_one_complete_tax_year(lakehouse_client):
    """Candle Bottle's fiscal year spans two calendar years and is still one year."""
    body = lakehouse_client.get("/api/scope/client/1001").json()

    coverage = {int(year): months for year, months in body["months_of_payroll"].items()}
    assert coverage.get(2023) == 12, "the 53-week fiscal year is complete, not partial"
    assert body["complete_years"] == [2023]
    assert body["default_year"] == 2023

    # The tail of payroll that falls into the NEXT fiscal year is a real sliver,
    # and reporting it as 8 months of TY2024 overstated it by a factor of four.
    assert coverage.get(2024, 0) < 12


def test_a_calendar_filer_is_unaffected(lakehouse_client):
    """The fix must not move clients whose fiscal year is the calendar year."""
    body = lakehouse_client.get("/api/scope/client/2003").json()

    coverage = {int(year): months for year, months in body["months_of_payroll"].items()}
    assert coverage.get(2023) == 12
    assert coverage.get(2024) == 12
    assert 2023 in body["complete_years"] and 2024 in body["complete_years"]


def test_coverage_never_exceeds_a_full_year(lakehouse_client):
    """A 53-week window touches 14 calendar months; the UI reads this out of 12."""
    for account_id in (1001, 2001, 2003):
        body = lakehouse_client.get(f"/api/scope/client/{account_id}").json()
        for year, months in body["months_of_payroll"].items():
            assert 1 <= months <= 12, f"account {account_id} TY{year} reported {months}"
