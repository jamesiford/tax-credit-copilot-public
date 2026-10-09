"""A token minted by one read must resolve in another.

The per-client eligibility and One/Zero views render every row with a
`record_token` and link the employee drill to it. That drill is served by the
sealed workspace. When the two derived the token differently, every row on
those screens opened a 404 — and nothing failed, because each side was
internally consistent and no test crossed the boundary.
"""
from __future__ import annotations

import os

import pytest

from application.queries.get_eligibility import GetEligibilityQuery
from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery
from tests.certified import (
    CERTIFIED_PROGRAM_CODE,
    CERTIFIED_TAX_YEAR,
)
from tools.tokens import record_token


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def lakehouse_source(monkeypatch):
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")


def test_the_token_is_derived_from_the_client_year_not_the_run():
    """Keying it to a calculation_id makes it unresolvable outside that run."""
    first = record_token(1001, "GA_JTC", 2023, "48685377")
    assert first == record_token(1001, "GA_JTC", 2023, "48685377")
    assert first != record_token(2003, "GA_JTC", 2023, "48685377")
    assert first != record_token(1001, "GA_JTC", 2024, "48685377")
    assert "48685377" not in first
    assert len(first) == 24


def test_the_sealed_drill_resolves_a_token_the_per_client_view_minted(lakehouse_source):
    from tools.reference_workspace import ReferenceWorkspaceService

    from application.wiring import get_mediator

    body = get_mediator().send(
        GetEligibilityQuery(
            tax_year=CERTIFIED_TAX_YEAR, state="GA", account_id=1001, limit=25
        )
    )
    assert body["program_code"] == CERTIFIED_PROGRAM_CODE

    state = ReferenceWorkspaceService().get()
    for row in body["rows"]:
        assert state.token_to_employee.get(row["record_token"]) == row["employee_id"], (
            "the drill would 404 on this row"
        )


def test_the_matrix_mints_the_same_token_as_the_population(lakehouse_source):
    from application.wiring import get_mediator

    mediator = get_mediator()
    population = mediator.send(
        GetEligibilityQuery(
            tax_year=CERTIFIED_TAX_YEAR, state="GA", account_id=1001, limit=500
        )
    )
    matrix = mediator.send(
        GetOneZeroMatrixQuery(tax_year=CERTIFIED_TAX_YEAR, state="GA", account_id=1001)
    )

    by_employee = {r["employee_id"]: r["record_token"] for r in population["rows"]}
    checked = 0
    for row in matrix["matrix"]:
        expected = by_employee.get(row["employee_id"])
        if expected is None:
            continue
        assert row["record_token"] == expected
        checked += 1
    assert checked > 0, "no overlap between the two reads to compare"
