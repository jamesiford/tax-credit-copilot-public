"""Tests for `tools.simulation` — What-If Simulator core.

Covers:
- Direction-aware: positive `new_hires` → projected > baseline; negative → projected < baseline.
- City → state resolution covers the 26 cities in `_CITY_MAP`.
- Two-letter state codes pass through directly.
- Unknown locations fall back to GA / Fulton.
- Validation: `new_hires == 0` raises.
- Result shape: baseline / projected / delta / citation always present.
"""
from __future__ import annotations

import pytest

from tools.simulation import _CITY_MAP, _resolve_location, simulate_hiring


# ---------------------------------------------------------------------------
# Location resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("city", sorted(_CITY_MAP.keys()))
def test_every_city_in_map_resolves_to_a_state(city):
    """Every entry in `_CITY_MAP` must resolve to a 2-letter state + county."""
    state, county = _resolve_location(city)
    assert len(state) == 2 and state.isupper()
    assert county and isinstance(county, str)


def test_atlanta_resolves_to_ga_fulton():
    assert _resolve_location("Atlanta") == ("GA", "Fulton")


def test_state_code_passes_through():
    state, county = _resolve_location("ga")
    assert state == "GA"
    assert county is None


def test_unknown_location_falls_back_to_ga_fulton():
    """Per the prototype demo default."""
    assert _resolve_location("Mars") == ("GA", "Fulton")


def test_case_insensitive_lookup():
    a = _resolve_location("ATLANTA")
    b = _resolve_location("atlanta")
    c = _resolve_location("  Atlanta  ")
    assert a == b == c


# ---------------------------------------------------------------------------
# simulate_hiring — happy paths
# ---------------------------------------------------------------------------


def test_simulate_hiring_returns_well_formed_result():
    """Result shape contract — every key downstream callers expect."""
    r = simulate_hiring("Atlanta", new_hires=25)
    assert r["location_city_or_state"] == "Atlanta"
    assert r["resolved_state"] == "GA"
    assert r["resolved_county"] == "Fulton"
    assert r["new_hires"] == 25
    for bucket in ("baseline", "projected"):
        assert "net_new_headcount" in r[bucket]
        assert "annual_credit_usd" in r[bucket]
        assert "lifetime_credit_usd" in r[bucket]
    assert r["delta"]["annual_credit_usd"] == (
        r["projected"]["annual_credit_usd"] - r["baseline"]["annual_credit_usd"]
    )
    assert r["citation"]


def test_positive_new_hires_yields_positive_or_zero_delta():
    """Adding FTEs in a state with an active pack should never reduce the credit."""
    r = simulate_hiring("Atlanta", new_hires=25)
    assert r["delta"]["annual_credit_usd"] >= 0
    assert r["delta"]["lifetime_credit_usd"] >= 0


def test_negative_new_hires_yields_negative_or_zero_delta():
    """Removing FTEs (layoffs/closure) must never increase the credit."""
    r = simulate_hiring("Atlanta", new_hires=-25)
    assert r["delta"]["annual_credit_usd"] <= 0
    assert r["delta"]["lifetime_credit_usd"] <= 0
    assert r["new_hires"] == -25


def test_layoff_in_high_threshold_state_can_zero_the_credit():
    """A large layoff in TN (25-job threshold) should push qualifying jobs to zero."""
    r = simulate_hiring("Nashville", new_hires=-500)
    assert r["projected"]["annual_credit_usd"] == 0
    assert r["projected"]["lifetime_credit_usd"] == 0


def test_lifetime_equals_annual_times_years_invariant():
    """Lifetime credit must equal annual × benefit_period_years for both buckets."""
    r = simulate_hiring("Atlanta", new_hires=10)
    # GA JTC benefit period is 5 years.
    if r["baseline"]["annual_credit_usd"]:
        assert r["baseline"]["lifetime_credit_usd"] == r["baseline"]["annual_credit_usd"] * 5
    if r["projected"]["annual_credit_usd"]:
        assert r["projected"]["lifetime_credit_usd"] == r["projected"]["annual_credit_usd"] * 5


# ---------------------------------------------------------------------------
# simulate_hiring — validation
# ---------------------------------------------------------------------------


def test_zero_new_hires_raises():
    """A zero-delta simulation is meaningless and must be rejected."""
    with pytest.raises(ValueError, match="non-zero"):
        simulate_hiring("Atlanta", new_hires=0)


# ---------------------------------------------------------------------------
# Per-state spot checks (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("location,expected_state", [
    ("Atlanta", "GA"),
    ("Nashville", "TN"),
    ("Charlotte", "NC"),
    ("Tampa", "GA"),  # unknown city → GA fallback
    ("CO", "CO"),
    ("ny", "NY"),
])
def test_resolved_state_matches_expectation(location, expected_state):
    r = simulate_hiring(location, new_hires=10)
    assert r["resolved_state"] == expected_state


def test_tx_simulation_has_no_state_credit():
    """TX has no state rule pack; the simulator honestly returns $0 state credit
    (federal WOTC still applies) rather than faking a GA fallback."""
    r = simulate_hiring("Houston", new_hires=20)
    assert r["resolved_state"] == "TX"
    assert r["baseline"]["annual_credit_usd"] == 0
    assert r["projected"]["annual_credit_usd"] == 0
    assert "no state rule pack" in r["citation"].lower()
