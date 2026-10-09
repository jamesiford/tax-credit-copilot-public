"""Per-client eligibility. [ENGINE-CONVERGENCE Phase 2]

The acceptance criterion for threading a client key through the calculation is
stated in the convergence spec: *two clients calculated in one process yield
independent, correctly attributed results.* That is what this file asserts.

It matters more than it looks. Until this query existed, "who qualifies" could
only answer for the certified reference run, so the product read as a
one-client demo. The engine was never the limitation — the wiring was.

The live-Fabric cases skip cleanly. The reference client's certified figures are
pinned by `test_engine_parity_reference.py`; nothing here may restate them,
because a second copy of a number is a second thing to forget to update.
"""
from __future__ import annotations

import os

import pytest

from application.queries.get_eligibility import (
    EligibilityNotAvailable,
    GetEligibilityQuery,
)


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


@pytest.fixture
def lakehouse_source(monkeypatch):
    """Point the payroll reader at the lakehouse for one test.

    `conftest.py` pins `DATA_SOURCE=csv` for the whole suite so the parity gate
    can never accidentally depend on a network. The CSV source holds the
    reference client and nobody else, so a per-client test that forgot this
    would read account 1001's payroll under every account id and quietly pass.
    """
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")


# --- the query object itself: cheap, offline, and worth pinning ---------------


def test_status_filter_rejects_an_unknown_value():
    """A typo must not silently widen the population to everybody."""
    with pytest.raises(ValueError, match="status must be one of"):
        GetEligibilityQuery(tax_year=2023, state="GA", status="eligible")


def test_paging_bounds_are_enforced():
    with pytest.raises(ValueError, match="limit must be between"):
        GetEligibilityQuery(tax_year=2023, state="GA", limit=5000)
    with pytest.raises(ValueError, match="offset cannot be negative"):
        GetEligibilityQuery(tax_year=2023, state="GA", offset=-1)


def test_a_sort_is_a_whitelisted_column_ordered_before_the_page_is_cut():
    """29 Sep: every table sorts. Here it has to happen in SQL, BEFORE the
    OFFSET, or page one of "by total hours" is the top of fifty rows rather
    than of the population. The key arrives from a query string, so it is a
    whitelist, never interpolated."""
    from infrastructure.persistence.gold_reader import ELIGIBILITY_SORTS, _stmt_eligibility_page

    with pytest.raises(ValueError, match="sort must be one of"):
        GetEligibilityQuery(tax_year=2023, state="GA", sort="employee_id; DROP TABLE x")
    with pytest.raises(ValueError, match="order must be"):
        GetEligibilityQuery(tax_year=2023, state="GA", order="sideways")

    sql, _ = _stmt_eligibility_page(
        1001, 2023, "r", 35, 636, 0.05, "all", False, "", 50, 0, "total_hours", "desc",
    )
    assert "ORDER BY total_hours DESC, employee_id ASC OFFSET" in sql
    sql, _ = _stmt_eligibility_page(1001, 2023, "r", 35, 636, 0.05, "all", False, "", 50, 0, "nope", "asc")
    assert "ORDER BY employee_id ASC OFFSET" in sql
    assert set(ELIGIBILITY_SORTS) == set(
        __import__("application.queries.get_eligibility", fromlist=["_SORTS"])._SORTS
    )


def test_an_unmapped_state_is_declined_by_name(client):
    """A state with no programme is a 404 with a reason, not an empty list."""
    response = client.get("/api/eligibility/2023", params={"state": "ZZ"})
    assert response.status_code == 404
    assert "no programme maps to state" in response.json()["detail"]


def test_an_unauthored_year_is_declined_rather_than_priced(client):
    """[ADR-005] Statute is not inherited across years.

    Pricing 2015 under 2023's floors would be a wrong answer wearing the
    costume of a right one. Regression: `load_year_pack` raises
    `FileNotFoundError`, so a handler catching only `ValueError` turned this
    into a 500.
    """
    response = client.get("/api/eligibility/2015", params={"state": "GA"})
    assert response.status_code == 404
    detail = response.json()["detail"].lower()
    assert "2015" in detail


def test_proximity_also_declines_an_unauthored_year(client):
    """Same defect, same fix — the two handlers must agree on what a decline is."""
    response = client.get("/api/proximity/2015", params={"state": "GA"})
    assert response.status_code == 404
    assert "2015" in response.json()["detail"]


# --- the acceptance criterion ------------------------------------------------


@pytest.mark.parametrize("account_id", [1001, 2003])
def test_a_client_year_answers_with_both_methods(lakehouse_source, account_id):
    """Every employee carries a Min-Max verdict AND a Pay Period verdict.

    The year is the one each client's gold actually holds. The population is
    READ now, not recomputed, so asking for a year no run has reached is
    answered with `not_calculated` rather than an engine pass — which is the
    honest answer and the same one the trend grid gives.
    """
    from application.wiring import get_mediator

    tax_year = 2023 if account_id == 1001 else 2025
    body = get_mediator().send(
        GetEligibilityQuery(
            tax_year=tax_year, state="GA", account_id=account_id, limit=5,
        )
    )

    assert body["account_id"] == account_id
    assert body["calculation_state"] == "calculated"
    assert body["employees_evaluated"] > 0
    for row in body["rows"]:
        assert set(row["min_max"]) >= {"eligible", "passed_hours", "passed_wages"}
        assert set(row["pay_period"]) >= {"eligible", "passed_hours", "passed_wages"}
        # The population is a join, so a row exists even when neither passes.
        assert row["status"] in {"both", "min_max_only", "pay_period_only", "neither"}


def test_a_year_no_run_reached_is_a_statement_not_a_zero(lakehouse_source):
    """"Nobody qualifies" and "we have not looked" are different answers.

    Before the population was read from Gold this could not happen: the handler
    computed one on demand for any year asked for, which is why nothing ever had
    to say so. An UNAUTHORED year declines earlier and by name — this is about
    an authored year with no run behind it.
    """
    from application.wiring import get_mediator

    body = get_mediator().send(
        GetEligibilityQuery(tax_year=2020, state="GA", account_id=1001)
    )
    assert body["calculation_state"] == "not_calculated"
    assert body["employees_evaluated"] == 0
    assert "not a zero" in body["message"]


def test_two_clients_in_one_process_stay_independent(lakehouse_source):
    """The Phase 2 acceptance criterion, stated as a test.

    The failure this guards against is a cached or module-global run leaking
    one client's population into another's answer — which is precisely what the
    single sealed workspace did.
    """
    from application.wiring import get_mediator

    mediator = get_mediator()
    first = mediator.send(GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001))
    second = mediator.send(GetEligibilityQuery(tax_year=2023, state="GA", account_id=2003))
    first_again = mediator.send(GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001))

    assert first["employees_evaluated"] != second["employees_evaluated"]
    assert first["account_id"] == 1001 and second["account_id"] == 2003
    # Re-asking after another client must return the first answer unchanged.
    assert first_again["employees_evaluated"] == first["employees_evaluated"]
    assert first_again["min_max_eligible"] == first["min_max_eligible"]


def test_the_per_client_read_agrees_with_the_certified_figures(lakehouse_source):
    """The reference client, asked through the product path, must tie out.

    This is the join between the two halves of the system. `reference_workspace`
    counts `step1.common_totals`; this handler runs the production engine over
    the same client-year. If they disagree, one of the two screens in the demo
    is wrong, and the eligible counts alone will not reveal it — the first cut
    of this handler reported 539/656 correctly while counting 10,080 employees,
    because it took its denominator from the two average sets instead of from
    everyone with payroll in the window.
    """
    from application.wiring import get_mediator
    from tests.certified import (
        CERTIFIED_EMPLOYEES,
        CERTIFIED_MIN_MAX_ELIGIBLE,
        CERTIFIED_PAY_PERIOD_ELIGIBLE,
    )

    body = get_mediator().send(
        GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001)
    )

    assert body["employees_evaluated"] == CERTIFIED_EMPLOYEES
    assert body["min_max_eligible"] == CERTIFIED_MIN_MAX_ELIGIBLE
    assert body["pay_period_eligible"] == CERTIFIED_PAY_PERIOD_ELIGIBLE
    # Every employee is accounted for in exactly one reconciliation bucket.
    assert sum(body["reconciliation"].values()) == CERTIFIED_EMPLOYEES


def test_record_tokens_do_not_leak_the_employee_id(lakehouse_source):
    """Employee IDs must not enter a URL path. The drill-in is keyed by token."""
    from application.wiring import get_mediator

    body = get_mediator().send(
        GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001, limit=5)
    )
    for row in body["rows"]:
        assert row["employee_id"] not in row["record_token"]
        assert len(row["record_token"]) == 24


def test_the_window_comes_from_the_client_not_a_global_setting(lakehouse_source):
    """Two clients with different fiscal years must not share one window.

    Candle Bottle runs a 53-week payroll calendar, 2023-07-28 to 2024-08-02.
    The synthetic clients run calendar years. Both are read from each client's
    own `EntityFiscalYearRules`, so the difference is a fact, not a setting.
    """
    from application.wiring import get_mediator

    reference = get_mediator().send(
        GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001)
    )
    assert reference["fiscal"]["begin"] == "2023-07-28"
    assert reference["fiscal"]["end"] == "2024-08-02"

    synthetic = get_mediator().send(
        GetEligibilityQuery(tax_year=2023, state="GA", account_id=2003)
    )
    assert synthetic["fiscal"]["begin"] == "2023-01-01"
    assert synthetic["fiscal"]["end"] == "2023-12-31"


def test_chat_request_accepts_client_scope_fields():
    from api.chat import ChatRequest

    req = ChatRequest(
        message="Which of our Georgia locations are closest to qualifying?",
        state="GA",
        client_id=1001,
        tax_year=2023,
        method="min_max",
    )

    assert req.client_id == 1001
    assert req.tax_year == 2023
    assert req.method == "min_max"


def test_chat_requires_a_selected_client_for_a_page_scoped_answer(client):
    response = client.post(
        "/api/chat",
        json={
            "message": "Which of these locations are closest to qualifying?",
            "state": "GA",
            "method": "min_max",
        },
    )

    assert response.status_code == 200
    body = response.text.lower()
    # WI-14: it now ASKS which client rather than refusing outright — but the
    # principle is unchanged. Nothing is answered, and it says it will not guess.
    assert "event: clarify" in body
    assert "no client is selected" in body
    assert "won't guess" in body
    assert "calculation_trail" not in body
    assert '"agent": "reportingagent"' not in body
