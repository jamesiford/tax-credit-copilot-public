"""Schema validation for every rule pack in `backend/rules/`.

Adding a new state credit is supposed to be JSON-only — these tests are the
guardrail that catches missing required fields, malformed `one_zero` blocks,
or unrecognized benefit shapes before they reach the UI as silently-wrong
numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.calculation.onezero import OneZeroMethodology

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def _all_pack_files() -> list[Path]:
    return sorted(RULES_DIR.glob("*.json"))


def _all_packs() -> list[tuple[str, dict]]:
    return [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in _all_pack_files()]


# ---------------------------------------------------------------------------
# File-level
# ---------------------------------------------------------------------------


def test_rules_dir_contains_expected_pack_count():
    """We ship 10 packs (9 state + 1 federal)."""
    assert len(_all_pack_files()) == 10


@pytest.mark.parametrize("path", _all_pack_files(), ids=lambda p: p.name)
def test_pack_is_valid_json(path):
    """Every pack must parse as JSON without errors."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Schema (parametrized across every pack)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_has_top_level_required_fields(name, pack):
    """Top-level shape: prototype verification + version + jurisdiction + credit + thresholds + benefit + filing."""
    required = [
        "_prototype_verification",
        "rule_pack_version",
        "jurisdiction",
        "credit",
        "thresholds",
        "benefit",
        "filing",
        "one_zero",
    ]
    missing = [k for k in required if k not in pack]
    assert not missing, f"{name} missing top-level fields: {missing}"


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_jurisdiction_block(name, pack):
    j = pack["jurisdiction"]
    assert "level" in j and j["level"] in ("federal", "state")
    assert "code" in j and isinstance(j["code"], str) and len(j["code"]) >= 2
    assert "name" in j


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_credit_block(name, pack):
    c = pack["credit"]
    for k in ("code", "name", "statutory_citation"):
        assert k in c and c[k], f"{name}: credit.{k} missing or empty"
    # Citation must look citation-shaped (contains a § or 'IRC' or similar).
    cit = c["statutory_citation"]
    assert any(marker in cit for marker in ("§", "IRC", "Code", "C.R.S.", "Stat", "G.S.", "T.C.A.")), (
        f"{name}: citation '{cit}' doesn't look like a real statutory citation"
    )


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_thresholds_block(name, pack):
    t = pack["thresholds"]
    assert "minimum_new_jobs" in t
    assert isinstance(t["minimum_new_jobs"], (int, float))
    assert t["minimum_new_jobs"] >= 0


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_benefit_shape_recognized(name, pack):
    """Benefit must be either flat per-job USD or pct-of-wages — nothing else."""
    b = pack["benefit"]
    assert "benefit_period_years" in b
    assert b["benefit_period_years"] >= 1
    has_flat = "amount_per_qualifying_job_usd" in b
    has_pct = "amount_per_qualifying_job_pct_of_wages" in b
    assert has_flat ^ has_pct, (
        f"{name}: benefit must declare exactly one of "
        "amount_per_qualifying_job_usd / amount_per_qualifying_job_pct_of_wages"
    )


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_filing_block(name, pack):
    f = pack["filing"]
    assert "window" in f and isinstance(f["window"], str) and f["window"].strip()
    assert "cycle" in f and f["cycle"] in ("annual", "quarterly", "pre-application", "per-hire")


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_one_zero_block(name, pack):
    """Every pack must carry an `one_zero` block with the required eligibility floors.

    Allowed enum values reflect real packs in the library:
      - wage_basis: 'regular' (most packs) | 'all_remuneration' (NY Excelsior) | 'gross'
      - geographic_granularity: 'unit' (GA/CO) | 'state'/'statewide' (most) |
        'county' (SC/TN/NC) | 'national'
    """
    oz = pack["one_zero"]
    required = (
        "min_weekly_hours",
        "min_weekly_wages",
        "wage_basis",
        "geographic_granularity",
        "pt_aggregation",
        "headcount_unit_field",
    )
    missing = [k for k in required if k not in oz]
    assert not missing, f"{name}: one_zero block missing fields: {missing}"
    assert oz["min_weekly_hours"] > 0
    # min_weekly_wages can legitimately be 0 for federal WOTC (no statutory wage floor).
    assert oz["min_weekly_wages"] >= 0
    assert oz["wage_basis"] in ("regular", "gross", "all_remuneration")
    assert oz["geographic_granularity"] in ("unit", "state", "statewide", "county", "national")
    assert isinstance(oz["pt_aggregation"], bool)
    # [I2] CALC-06 — when declared, entity_combination must be a valid treatment.
    if "entity_combination" in oz:
        assert oz["entity_combination"] in ("required", "permitted", "prohibited")
    # [H1] CALC-03 — when declared, thresholds_by_year maps year -> floor block.
    if "thresholds_by_year" in oz:
        for yr, block in oz["thresholds_by_year"].items():
            int(yr)  # year key must be numeric
            assert "min_weekly_hours" in block
            assert block["min_weekly_hours"] > 0
            if "pt_weight" in block and block["pt_weight"] is not None:
                assert 0 < block["pt_weight"] <= 1
    # Any `methodology` block a pack carries must parse. `from_pack_json` raises
    # on an unknown or invalid key, so this is the gate that catches a typo
    # before it silently reverts a pack to the certified defaults.
    OneZeroMethodology.from_pack_json(oz.get("methodology"))


def test_methodology_defaults_are_the_certified_rules():
    """An absent `methodology` block inherits v7, so no pack needs editing.

    These literals are the rules certified with the partner. Changing a default
    silently re-prices every state, so the change has to break this test first.
    """
    m = OneZeroMethodology.from_pack_json(None)
    assert m.minimum_pay_period_days == 7
    assert m.short_periods_excluded_from_numerator is False
    assert m.pay_period_denominator_mode == "actual_span"
    assert m.min_max_span_mode == "exclusive_days"
    assert m.count_zero_hour_periods is True
    assert m.average_decimals == 2
    assert m.exclude_off_cycle_periods is False


def test_methodology_partial_override_keeps_other_defaults():
    m = OneZeroMethodology.from_pack_json({"minimum_pay_period_days": 0})
    assert m.minimum_pay_period_days == 0
    assert m.pay_period_denominator_mode == "actual_span"


def test_methodology_rejects_unknown_key():
    """A typo must fail loudly, not silently revert to defaults."""
    with pytest.raises(ValueError, match="minimum_pay_period_day"):
        OneZeroMethodology.from_pack_json({"minimum_pay_period_day": 7})


@pytest.mark.parametrize("block", [
    {"pay_period_denominator_mode": "frequency_codes"},
    {"min_max_span_mode": "inclusive"},
    {"minimum_pay_period_days": -1},
])
def test_methodology_rejects_invalid_value(block):
    with pytest.raises(ValueError):
        OneZeroMethodology.from_pack_json(block)


@pytest.mark.parametrize("name,pack", _all_packs(), ids=lambda p: p if isinstance(p, str) else "")
def test_pack_version_format(name, pack):
    """Versions follow `v?MAJOR.MINOR.PATCH`."""
    v = pack["rule_pack_version"]
    parts = v.lstrip("v").split(".")
    assert len(parts) == 3, f"{name}: version '{v}' not semver"
    for p in parts:
        int(p)  # raises if non-numeric


# ---------------------------------------------------------------------------
# Cross-pack invariants
# ---------------------------------------------------------------------------


def test_credit_codes_are_unique():
    """No two packs can share a `credit.code`."""
    codes = [pack["credit"]["code"] for _, pack in _all_packs()]
    assert len(codes) == len(set(codes)), f"duplicate credit codes: {codes}"


def test_filenames_match_jurisdiction_pattern():
    """Filename convention: `<state>_<credit>.json` for state packs, `federal_*` for federal."""
    for path in _all_pack_files():
        pack = json.loads(path.read_text(encoding="utf-8"))
        level = pack["jurisdiction"]["level"]
        if level == "federal":
            assert path.name.startswith("federal_"), f"{path.name} federal pack must start with 'federal_'"
        else:
            assert path.name.startswith(pack["jurisdiction"]["code"].lower() + "_"), (
                f"{path.name} state pack must start with jurisdiction code prefix"
            )
