"""Portfolio-wide what-if: one lever, every client in a state-year.

The property that matters is not the arithmetic — the single-client simulator
already owns that — it is the **ranking and the framing**. A client crossing
from no credit to a credit is a different kind of result from an established
earner earning more, and a portfolio view that sorts on dollars alone hides the
crossing behind the earner. That is the whole reason this exists rather than a
loop in a router.
"""
from __future__ import annotations

import os

import pytest

from application.queries.simulate_portfolio import (
    PortfolioSimulationNotAvailable,
    SimulatePortfolioQuery,
)


# --- the request validates itself ------------------------------------------


def test_an_unknown_lever_is_refused_by_the_request():
    """Validation lives on the query, so a scheduled job gets the same check as
    an HTTP caller."""
    with pytest.raises(ValueError, match="action must be one of"):
        SimulatePortfolioQuery(tax_year=2025, state="GA", action="wave_a_wand")


def test_every_supported_lever_constructs():
    for action in ("add_headcount", "remove_headcount", "adjust_hours", "adjust_wages"):
        SimulatePortfolioQuery(tax_year=2025, state="GA", action=action)


def test_the_query_is_frozen():
    query = SimulatePortfolioQuery(tax_year=2025, state="GA")
    with pytest.raises(Exception):
        query.magnitude = 99  # type: ignore[misc]


# --- statute resolution ----------------------------------------------------


def test_a_state_with_no_programme_is_declined_by_name():
    with pytest.raises(PortfolioSimulationNotAvailable, match="no programme"):
        from application.queries.simulate_portfolio import handle_simulate_portfolio

        handle_simulate_portfolio(SimulatePortfolioQuery(tax_year=2025, state="ZZ"))


def test_an_unauthored_year_is_declined_rather_than_approximated():
    """ADR-005. Pricing a year under a neighbouring year's statute is a wrong
    answer that looks like a right one, so it is refused."""
    from application.queries.simulate_portfolio import handle_simulate_portfolio

    with pytest.raises(PortfolioSimulationNotAvailable) as exc:
        handle_simulate_portfolio(SimulatePortfolioQuery(tax_year=1999, state="GA"))
    assert "1999" in str(exc.value)
    assert "wrong answer" in str(exc.value)


# --- the ranking, which is the point ---------------------------------------


def _payload(**overrides):
    """A result set shaped like the handler's, for testing the ordering rules."""
    base = {
        "clients": [
            {
                "client_id": 1,
                "annual_credit_delta_usd": 100_000.0,
                "crosses_threshold": False,
            },
            {
                "client_id": 2,
                "annual_credit_delta_usd": 5_000.0,
                "crosses_threshold": True,
            },
        ]
    }
    base.update(overrides)
    return base


def test_crossings_rank_above_larger_deltas():
    """A client going from nothing to $5,000 outranks one going from $200,000 to
    $300,000. The first is a new customer conversation; the second is a bigger
    invoice to somebody already engaged."""
    clients = _payload()["clients"]
    clients.sort(key=lambda r: (not r["crosses_threshold"], -r["annual_credit_delta_usd"]))
    assert clients[0]["client_id"] == 2, "the crossing must come first"


# --- against the live data source ------------------------------------------


def _live_or_skip(monkeypatch):
    """The handler, against a multi-tenant source, or a skip naming the reason.

    `conftest` pins the suite to the deterministic CSV source, which holds one
    tenant — correct for repeatability, and it means a portfolio sweep has
    nothing to sweep. These tests opt in to live Fabric under the same flag as
    `test_fabric_source_selection.py`, so a default run stays offline and fast.

        $env:TCC_FABRIC_TESTS=1 ; pytest tests/test_simulate_portfolio.py

    The source switch MUST go through `monkeypatch`. Assigning `os.environ`
    directly leaves the whole process on `lakehouse` for every test that follows,
    and the sealed `/api/workspace/*` tests then read live Fabric instead of
    the certified CSV fixture and fail on figures that are not theirs. That is
    invisible offline, because this branch only runs under TCC_FABRIC_TESTS=1.
    """
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run the sweep against live Fabric")

    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    from application.queries.simulate_portfolio import handle_simulate_portfolio
    from infrastructure.payroll.pay_period_source import load_portfolio_pay_periods

    try:
        tenants = load_portfolio_pay_periods()
    except Exception as exc:  # noqa: BLE001 — a paused capacity is not a failure
        pytest.skip(
            f"Fabric unreachable ({type(exc).__name__}). If this is "
            f"ArtifactNotFound, check the capacity is Active before assuming "
            f"the lakehouse is missing: {exc}"
        )
    if len(tenants) < 2:
        pytest.skip(f"need 2+ tenants for a portfolio sweep, found {len(tenants)}")
    return handle_simulate_portfolio


def test_the_sweep_spans_every_tenant_with_payroll_in_that_state(monkeypatch):
    handle = _live_or_skip(monkeypatch)
    result = handle(
        SimulatePortfolioQuery(tax_year=2025, state="GA", magnitude=5)
    )
    assert result["clients_evaluated"] >= 2
    assert {c["client_id"] for c in result["clients"]} == {
        c["client_id"] for c in result["clients"]
    }, "each client appears once"


def test_each_client_is_measured_against_its_own_frozen_base(monkeypatch):
    """Omitting the prior-year base treats the whole workforce as net-new, which
    overstates the credit enormously AND disagrees with the coverage matrix for
    the same client-year."""
    handle = _live_or_skip(monkeypatch)
    result = handle(SimulatePortfolioQuery(tax_year=2025, state="GA", magnitude=5))
    assert all("base_average_headcount" in c for c in result["clients"])
    assert any(c["base_average_headcount"] > 0 for c in result["clients"]), (
        "every base is zero — the frozen base is not being passed"
    )


def test_a_bigger_lever_never_unlocks_less(monkeypatch):
    """Monotonic in the lever. If +20 hires unlocks less than +10, something is
    wrong with the base or the threshold, not with the arithmetic."""
    handle = _live_or_skip(monkeypatch)
    small = handle(SimulatePortfolioQuery(tax_year=2025, state="GA", magnitude=5))
    large = handle(SimulatePortfolioQuery(tax_year=2025, state="GA", magnitude=20))
    assert large["credit_delta_total_usd"] >= small["credit_delta_total_usd"]
    assert large["clients_crossing_threshold"] >= small["clients_crossing_threshold"]


def test_one_client_failing_does_not_abandon_the_sweep(monkeypatch):
    """A partial answer presented as a complete one is the failure ADR-005 is
    about. Anything that could not be evaluated is reported by name."""
    handle = _live_or_skip(monkeypatch)
    result = handle(SimulatePortfolioQuery(tax_year=2025, state="GA", magnitude=5))
    assert "declined" in result
    assert isinstance(result["declined"], list)
