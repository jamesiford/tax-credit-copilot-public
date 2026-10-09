"""Tests for `tools.credit_math` — the rule-pack-driven credit calculations.

This is one of the most stakeholder-visible modules: every dollar amount on
the Overview KPI strip, Credit Portfolio, Simulator, and Value & Billing
ultimately flows through `apply_one_zero_state_credit()` — the statutory
One/Zero net-new benefit math. These tests pin the math against each rule
pack's documented shape.
"""
from __future__ import annotations

import pytest

from tools.credit_math import (
    STATE_TO_PACK,
    apply_one_zero_state_credit,
    load_pack_one_zero,
)
from domain.calculation.onezero import OneZeroPack


# ---------------------------------------------------------------------------
# apply_one_zero_state_credit — happy paths (net-new Average Monthly Headcount)
# ---------------------------------------------------------------------------


def test_ga_per_job_math_lifetime_is_annual_times_years():
    """GA JTC: 14 net-new (avg 14, prior 0) − 2 threshold = 12 qualifying ×
    $3,500/job × 5 years = $210,000 lifetime."""
    result = apply_one_zero_state_credit("GA", average_headcount=14.0)
    assert result["no_state_pack"] is False
    assert result["credit_code"] == "GA_JTC"
    assert result["threshold"] == 2.0
    assert result["qualifying_jobs"] == 12.0
    assert result["amount_per_job_usd"] == 3500
    assert result["annual_credit_usd"] == 12 * 3500
    assert result["benefit_period_years"] == 5
    assert result["lifetime_credit_usd"] == 12 * 3500 * 5


def test_state_code_is_case_insensitive():
    """`apply_one_zero_state_credit('ga', ...)` must work the same as 'GA'."""
    lower = apply_one_zero_state_credit("ga", average_headcount=10.0)
    upper = apply_one_zero_state_credit("GA", average_headcount=10.0)
    assert lower["credit_code"] == upper["credit_code"]
    assert lower["annual_credit_usd"] == upper["annual_credit_usd"]


def test_below_threshold_returns_zero_qualifying():
    """Net-new under the statutory threshold yields zero qualifying jobs."""
    # SC JTC threshold = 5 — anything <5 net new is below.
    result = apply_one_zero_state_credit("SC", average_headcount=4.0)
    assert result["qualifying_jobs"] == 0
    assert result["annual_credit_usd"] == 0
    assert result["lifetime_credit_usd"] == 0


def test_negative_net_new_clamped_to_zero():
    """A contraction (prior > current) must NOT produce a negative credit."""
    result = apply_one_zero_state_credit("GA", average_headcount=10.0, prior_period_average_headcount=60.0)
    assert result["qualifying_jobs"] == 0
    assert result["annual_credit_usd"] == 0
    assert result["lifetime_credit_usd"] == 0


# ---------------------------------------------------------------------------
# apply_one_zero_state_credit — pct-of-wages shape (NY Excelsior)
# ---------------------------------------------------------------------------


def test_ny_excelsior_uses_pct_of_wages_path():
    """NY Excelsior is a pct-of-wages benefit, not per-job flat amount."""
    result = apply_one_zero_state_credit("NY", average_headcount=80.0)
    assert result["credit_code"] == "NY_EXCELSIOR"
    if result["qualifying_jobs"] > 0:
        assert result["annual_credit_usd"] > 0
        assert result["lifetime_credit_usd"] == (
            result["annual_credit_usd"] * result["benefit_period_years"]
        )


def test_ny_negative_net_new_returns_zero():
    """NY Excelsior: a contraction scenario must return $0, not a negative credit."""
    result = apply_one_zero_state_credit("NY", average_headcount=5.0, prior_period_average_headcount=30.0)
    assert result["qualifying_jobs"] == 0
    assert result["annual_credit_usd"] == 0


# ---------------------------------------------------------------------------
# apply_one_zero_state_credit — TX (no state pack) fallback
# ---------------------------------------------------------------------------


def test_tx_returns_structured_no_state_pack():
    """TX has no state pack; the response must be honest about that."""
    result = apply_one_zero_state_credit("TX", average_headcount=99.0)
    assert result["no_state_pack"] is True
    assert result["credit_code"] is None
    assert result["annual_credit_usd"] == 0
    assert result["lifetime_credit_usd"] == 0
    assert "no state-level rule pack" in result["message"].lower()
    assert "GA" in result["message"]


def test_no_state_pack_message_lists_supported_states():
    """The fallback message must enumerate every supported state."""
    result = apply_one_zero_state_credit("XX", average_headcount=10.0)
    assert result["no_state_pack"] is True
    for state in STATE_TO_PACK:
        assert state in result["message"]


# ---------------------------------------------------------------------------
# apply_one_zero_state_credit — parametrized across every state pack
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", sorted(STATE_TO_PACK.keys()))
def test_every_state_pack_produces_well_formed_result(state):
    """Every state in STATE_TO_PACK must produce a complete result dict."""
    result = apply_one_zero_state_credit(state, average_headcount=200.0)
    assert result["no_state_pack"] is False
    assert result["state"] == state
    assert result["credit_code"]
    assert result["citation"]
    assert result["threshold"] is not None
    assert result["benefit_period_years"] >= 1
    assert result["annual_credit_usd"] >= 0
    assert result["lifetime_credit_usd"] == (
        result["annual_credit_usd"] * result["benefit_period_years"]
    )



# ---------------------------------------------------------------------------
# load_pack_one_zero
# ---------------------------------------------------------------------------


def test_load_pack_one_zero_for_ga_returns_canonical_floors():
    """GA pack One/Zero block carries the partner's canonical floors (35 hrs / $680/wk)."""
    pack = load_pack_one_zero("GA")
    assert pack is not None
    assert isinstance(pack, OneZeroPack)
    assert pack.min_weekly_hours == 35.0
    assert pack.min_weekly_wages == 680.0
    # [L5] CALC-11 / DISC-14 — the partner (June 11) clarified GA uses ALL REMUNERATION
    # for the weekly-wage test, with non-wage codes (mileage) suppressed.
    assert pack.wage_basis == "all_remuneration"
    assert "Regular" in pack.included_pay_codes
    assert "Mileage" in pack.excluded_pay_codes
    assert pack.geographic_granularity == "unit"
    assert pack.headcount_unit_field == "Worksite_ID"


def test_load_pack_one_zero_resolves_workbook_2024_floor():
    """The partner-modified GA methodology workbook explicitly shows 2024 = $686/week."""
    pack = load_pack_one_zero("GA", tax_year=2024)

    assert pack.min_weekly_hours == 35.0
    assert pack.min_weekly_wages == 686.0


def test_load_pack_one_zero_accepts_credit_code():
    """Should resolve by credit code as well as by state code."""
    by_state = load_pack_one_zero("GA")
    by_code = load_pack_one_zero("GA_JTC")
    assert by_state.min_weekly_hours == by_code.min_weekly_hours
    assert by_state.min_weekly_wages == by_code.min_weekly_wages


def test_load_pack_one_zero_unknown_returns_none():
    """Unknown state/code must return None, not raise."""
    assert load_pack_one_zero("ZZ") is None
    assert load_pack_one_zero("BOGUS_CODE") is None


def test_load_pack_one_zero_federal_pack_resolvable_by_code():
    """Federal packs aren't in STATE_TO_PACK but should still resolve by code."""
    pack = load_pack_one_zero("FED_WOTC")
    # Federal WOTC ships with a one_zero block in the prototype.
    assert pack is not None


# ---------------------------------------------------------------------------
# apply_one_zero_state_credit — statutory engine output → benefit math
# ---------------------------------------------------------------------------


def test_one_zero_no_prior_period_treats_full_avg_as_net_new():
    """With prior_period=0 the entire Average Headcount is net-new."""
    result = apply_one_zero_state_credit("GA", average_headcount=50.0)
    # net_new = 50 - 0 - 2 (threshold) = 48 qualifying
    assert result["qualifying_jobs"] == 48
    assert result["annual_credit_usd"] == 48 * 3500
    assert result["basis"] == "one_zero"
    assert result["average_headcount"] == 50.0
    assert result["prior_period_average_headcount"] == 0.0


def test_one_zero_with_prior_period_uses_delta():
    """Year-over-year delta drives qualifying-jobs math."""
    result = apply_one_zero_state_credit(
        "GA", average_headcount=60.0, prior_period_average_headcount=40.0
    )
    # delta = 60 - 40 = 20; qualifying = 20 - 2 = 18
    assert result["qualifying_jobs"] == 18
    assert result["annual_credit_usd"] == 18 * 3500


def test_one_zero_negative_delta_returns_zero():
    """If prior period was larger than current, qualifying must be zero."""
    result = apply_one_zero_state_credit(
        "GA", average_headcount=10.0, prior_period_average_headcount=30.0
    )
    assert result["qualifying_jobs"] == 0
    assert result["annual_credit_usd"] == 0
    assert result["lifetime_credit_usd"] == 0


def test_one_zero_unknown_state_returns_no_state_pack():
    """One/Zero benefit math for TX must fall back to no_state_pack response."""
    result = apply_one_zero_state_credit("TX", average_headcount=100.0)
    assert result["no_state_pack"] is True


def test_one_zero_lifetime_is_annual_times_years_for_every_state():
    """Lifetime = annual × benefit_period_years invariant must hold per state."""
    for state in STATE_TO_PACK:
        r = apply_one_zero_state_credit(state, average_headcount=200.0)
        assert r["lifetime_credit_usd"] == r["annual_credit_usd"] * r["benefit_period_years"], (
            f"{state}: lifetime != annual × years"
        )
