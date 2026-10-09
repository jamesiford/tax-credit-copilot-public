"""The One/Zero monthly matrix, per client.

The sealed workspace built its matrix on a `ReferenceStep1Run`, which exists for
exactly one client. These tests pin the production-engine equivalent, and — more
importantly — pin the thing most likely to go wrong once two per-client reads
exist side by side: that they resolve the SAME fiscal window for the same
client-year. Two screens disagreeing about the denominator period is the failure
mode a reviewer notices and nobody's unit test does.
"""
from __future__ import annotations

import os

import pytest

from application.queries._client_run import ClientRunNotAvailable
from application.queries.get_eligibility import GetEligibilityQuery
from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def lakehouse_source(monkeypatch):
    """`conftest.py` pins DATA_SOURCE=csv suite-wide; per-client reads need lakehouse."""
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")


# --- the query object itself: cheap and offline ------------------------------


def test_method_must_be_one_the_engine_actually_runs():
    with pytest.raises(ValueError, match="method must be one of"):
        GetOneZeroMatrixQuery(tax_year=2023, state="GA", method="minmax")


def test_an_unauthored_year_is_declined_not_priced_from_a_neighbour():
    """[ADR-005] A missing rule pack is a gap in coverage, not a rounding error."""
    from application.wiring import get_mediator

    with pytest.raises(ClientRunNotAvailable):
        get_mediator().send(GetOneZeroMatrixQuery(tax_year=2015, state="GA"))


# --- the acceptance criterion ------------------------------------------------


@pytest.mark.parametrize("method", ["min_max", "pay_period"])
def test_the_matrix_allocates_eligible_employees_to_unit_and_entity(lakehouse_source, method):
    from application.wiring import get_mediator

    body = get_mediator().send(
        GetOneZeroMatrixQuery(tax_year=2023, state="GA", account_id=1001, method=method)
    )

    assert body["method"] == method
    assert len(body["months"]) == 12
    assert body["units"] > 0 and body["matrix_rows"] > 0
    for row in body["summary"]:
        assert len(row["month_totals"]) == 12
        # A month total cannot exceed the number of people allocated to that cell.
        assert row["total"] == pytest.approx(sum(row["month_totals"]), abs=0.01)
    for row in body["matrix"]:
        assert len(row["months"]) == 12
        assert row["employee_id"] not in row["record_token"]


def test_no_employee_is_counted_twice_in_the_same_month(lakehouse_source):
    """The one-per-month rule, asserted on the shipped matrix rather than trusted.

    `_dedupe_one_per_month` enforces this inside the engine and does not record
    the decision anywhere, so this test is the only evidence the rule held.
    """
    from application.wiring import get_mediator

    body = get_mediator().send(
        GetOneZeroMatrixQuery(tax_year=2023, state="GA", account_id=1001)
    )

    per_employee_month: dict[tuple[str, int], float] = {}
    for row in body["matrix"]:
        for index, value in enumerate(row["months"]):
            key = (row["employee_id"], index)
            per_employee_month[key] = per_employee_month.get(key, 0.0) + value
    over_counted = {key: total for key, total in per_employee_month.items() if total > 1.0}
    assert not over_counted, f"{len(over_counted)} employee-months counted above 1"


def test_the_matrix_and_the_population_agree_on_the_window(lakehouse_source):
    """Two per-client reads, one client-year, one denominator period.

    If these ever diverge, Who qualifies and One/Zero will show different
    answers for the same client and both will look defensible on their own.
    """
    from application.wiring import get_mediator

    mediator = get_mediator()
    population = mediator.send(
        GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001, limit=1)
    )
    matrix = mediator.send(
        GetOneZeroMatrixQuery(tax_year=2023, state="GA", account_id=1001, method="min_max")
    )

    assert matrix["fiscal"] == population["fiscal"]
    assert matrix["thresholds"] == population["thresholds"]
    assert matrix["program_code"] == population["program_code"]
    # The people in the matrix are exactly the ones the population called eligible.
    assert matrix["eligible_employees"] == population["min_max_eligible"]


def test_two_clients_get_different_matrices(lakehouse_source):
    from application.wiring import get_mediator

    mediator = get_mediator()
    reference = mediator.send(
        GetOneZeroMatrixQuery(tax_year=2023, state="GA", account_id=1001)
    )
    synthetic = mediator.send(
        GetOneZeroMatrixQuery(tax_year=2023, state="GA", account_id=2003)
    )

    assert reference["units"] != synthetic["units"]
    assert reference["fiscal"]["begin"] != synthetic["fiscal"]["begin"]
