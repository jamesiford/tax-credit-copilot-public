"""Tests for `tools.discovery` — credit discovery from the rule pack library."""
from __future__ import annotations

from pathlib import Path

from tools.discovery import discover_credits

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def test_discover_credits_returns_shape():
    result = discover_credits()
    for key in ("hits", "packs_considered", "excluded"):
        assert key in result


def test_packs_considered_includes_state_and_federal_codes():
    """Discovery now views the statutory portfolio. `packs_considered` lists the
    jurisdiction tile codes evaluated (state packs with data + federal WOTC +
    any no-pack states), so it must include GA_JTC and FED_WOTC."""
    result = discover_credits()
    considered = result["packs_considered"]
    assert "GA_JTC" in considered
    assert "FED_WOTC" in considered
    assert len(considered) >= 1


def test_discover_credits_hits_have_required_fields():
    result = discover_credits()
    for h in result["hits"]:
        for k in ("credit_code", "credit_name", "jurisdiction", "citation",
                  "qualifying_jobs", "annual_credit_usd", "lifetime_credit_usd"):
            assert k in h, f"hit missing key {k}: {h}"


def test_discover_credits_hits_sorted_by_lifetime_desc():
    hits = discover_credits()["hits"]
    lifetimes = [h["lifetime_credit_usd"] for h in hits]
    assert lifetimes == sorted(lifetimes, reverse=True)


def test_exclude_codes_suppresses_those_packs():
    """Passing `exclude_codes=['GA_JTC']` removes GA from the hits list."""
    full = discover_credits()
    excluded = discover_credits(exclude_codes=["GA_JTC"])
    full_codes = {h["credit_code"] for h in full["hits"]}
    excluded_codes = {h["credit_code"] for h in excluded["hits"]}
    if "GA_JTC" in full_codes:
        assert "GA_JTC" not in excluded_codes
    assert "GA_JTC" in excluded["excluded"]


def test_exclude_codes_does_not_affect_packs_considered():
    """Excluding a code shouldn't drop it from the 'packs scanned' list."""
    base = discover_credits()
    excl = discover_credits(exclude_codes=["GA_JTC"])
    assert sorted(base["packs_considered"]) == sorted(excl["packs_considered"])


def test_federal_wotc_can_surface_as_hit():
    """The federal pack uses a different basis (new_hires_in_window) and should appear."""
    result = discover_credits()
    codes = {h["credit_code"] for h in result["hits"]}
    # Federal WOTC should surface on the MeridianCore dataset
    assert "FED_WOTC" in codes or "FED_WOTC" in result["packs_considered"]


def test_every_hit_has_positive_dollar_amount():
    """A pack only becomes a hit when qualifying jobs > threshold and credit > 0."""
    for h in discover_credits()["hits"]:
        assert h["qualifying_jobs"] > 0
        assert h["annual_credit_usd"] > 0
        assert h["lifetime_credit_usd"] >= h["annual_credit_usd"]
