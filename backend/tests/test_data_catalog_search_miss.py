"""A catalog search that finds nothing says so, in words a model can act on. [CH-16e]

An empty table beside a generic "pass dataset=<name>" hint reads as "try again"; the model then guesses a
column. A miss now states that the data has nothing for the search, which is what the narrator prompt and the
Cowork skills tell the model to say.
"""
from __future__ import annotations

from application.capabilities.invoke import invoke
from tests.data_caps_fixture import data_service, person  # noqa: F401 - fixture


def catalog(**args):
    return invoke("data_catalog", args, person()).to_dict()


def test_a_search_with_no_match_says_the_data_has_nothing_for_it(data_service):  # noqa: F811
    result = catalog(search="commute")
    assert result["facts"]["dataset_count"] == 0
    notes = " ".join(result["facts"]["notes"])
    assert "has nothing for it" in notes and "do not guess a column name" in notes
    assert any("has nothing for it" in b.get("text", "") for b in result["blocks"])


def test_a_search_that_matches_carries_no_miss_note(data_service):  # noqa: F811
    assert "nothing for it" not in " ".join(catalog(search="hours")["facts"]["notes"])


def test_no_search_and_a_named_dataset_carry_no_miss_note(data_service):  # noqa: F811
    assert "nothing for it" not in " ".join(catalog()["facts"]["notes"])
    assert "nothing for it" not in " ".join(catalog(dataset="unit_month_summary")["facts"]["notes"])
