"""WI-17: a per-year designation, shown on every location-year, moving no figure.

The write path takes a location's minimum from its designation when one is
registered. For 1 October the designation is DISPLAY-ONLY — the engine does
not apply the partner's tier rules — so every source-schema entry must carry the same
minimum the rule pack would. These fail the moment one would change a
threshold.
"""
from __future__ import annotations

import pytest

from application.queries.get_unit_trend import _designation_at, _year_benefit
from data.designations import _SOURCE_DESIGNATIONS, designation_history

CODES = {"T1", "T1 B40", "T2", "T3", "T4", "MZ", "OZ", "LDCT"}
GA_YEARS = range(2020, 2026)


def _every_source_history():
    yield from _SOURCE_DESIGNATIONS.items()
    yield (2003, "GA_GA-001"), designation_history("GA_GA-001", 2003)  # the synthetic default


@pytest.mark.parametrize("key,history", list(_every_source_history()), ids=lambda v: str(v)[:40])
def test_no_designation_moves_a_minimum(key, history):
    client_id, unit_id = key
    for year in GA_YEARS:
        entry = _designation_at(unit_id, year, client_id)
        assert entry is not None, f"{key} has no designation in TY{year}"
        assert entry["designation"] in CODES, entry
        assert float(entry["min_new_jobs"]) == float(_year_benefit("GA_JTC", year)["threshold"]), (
            f"{key} TY{year}: designation {entry['designation']} carries minimum "
            f"{entry['min_new_jobs']}, the rule pack {_year_benefit('GA_JTC', year)['threshold']}. "
            f"Designation is display-only until the engine applies tier rules."
        )


def test_the_reference_client_is_never_assigned_a_designation():
    """Candle Bottle's designations are a fact we do not hold."""
    assert designation_history("GA_1134481", 1001) == []
    assert _designation_at("GA_1134481", 2023, 1001) is None


def test_a_unit_id_is_only_unique_within_a_client():
    """Every synthetic client has a GA_GA-001; GA-013's story is Cascade's alone."""
    assert _designation_at("GA_GA-013", 2021, 2001)["designation"] == "T1 B40"
    assert _designation_at("GA_GA-013", 2021, 2002)["designation"] == "T1"


def test_the_cascade_story_is_bottom_40_in_the_creation_year_only():
    """WI-18: T1 before, T1 B40 in TY2021 when the jobs were created, T1 after."""
    by_year = {y: _designation_at("GA_GA-013", y, 2001)["designation"] for y in GA_YEARS}
    assert by_year == {2020: "T1", 2021: "T1 B40", 2022: "T1", 2023: "T1", 2024: "T1", 2025: "T1"}


def test_the_legacy_worksite_registry_is_unchanged():
    assert designation_history("GA_MAC_OPS")[0]["tier"] == 2
