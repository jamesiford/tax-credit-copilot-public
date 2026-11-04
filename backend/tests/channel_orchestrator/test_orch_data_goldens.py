"""The nuanced data questions, as a set: enough of them, every kind, each with a tool sequence. [CH-16e]

`golden/data_use.json` is played by `test_orch_golden.py`, which asserts the gateway's tool sequence,
the arguments the platform (not the model) settled, the reply's wording, and, for every answer, that each
numeral in the final text is in the engine's facts or in the person's own words. This file holds the SET to
what the work package promises, and proves the one new assertion (`model_never_sees`) can fail.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from test_orch_golden import GOLDEN, play

CASES = json.loads((GOLDEN / "data_use.json").read_text(encoding="utf-8"))
KINDS = {
    "descriptive by location": "use_descriptive_by_location", "descriptive by month": "use_descriptive_by_month",
    "descriptive by designation": "use_descriptive_by_designation", "a name resolved first": "use_a_name_is_resolved",
    "method comparison": "use_compares_the_two_methods", "a why question": "use_why_question_takes",
    "a catalog miss": "refuse_a_column_the_catalog_does_not_list", "an invented column": "refuse_an_invented_column",
    "an employee-level ask": "lane_employee_rows", "a cross-client attempt": "scope_two_named_clients",
    "a capped result": "result_capped", "a timeout": "failure_a_timeout", "an out-of-model ask": "refuse_free_form_sql",
}


def test_there_are_at_least_twenty_five_nuanced_data_questions():
    assert len(CASES) >= 25 and len({c["name"] for c in CASES}) == len(CASES)


@pytest.mark.parametrize("kind, prefix", KINDS.items())
def test_every_kind_the_work_package_names_is_covered(kind, prefix):
    assert any(c["name"].startswith(prefix) for c in CASES), kind


def test_every_turn_asserts_its_tool_sequence_and_a_kind():
    for case in CASES:
        for turn in case["turns"]:
            assert "gateway" in turn["expect"] and "kind" in turn["expect"], case["name"]


def test_the_three_data_tools_are_each_asked_for_and_each_lane_is_exercised():
    asked = {call["tool"] for c in CASES for t in c["turns"] for step in t.get("model", []) for call in step.get("tools", [])}
    assert {"data_catalog", "data_query", "data_distinct_values", "client_trend", "client_eligibility", "book_rank"} <= asked
    sees = [c["name"] for c in CASES if any("model_never_sees" in t["expect"] for t in c["turns"])]
    assert len(sees) >= 3, "the user lane must be asserted on at least three questions"


def test_a_case_that_says_a_model_never_sees_something_it_does_see_fails():
    """A negative control: the catalog's own words ARE shown to the model, so claiming otherwise must fail."""
    leaky = {
        "name": "leaky", "turns": [{
            "say": "For Northwind, what can I ask about the unit month summary?",
            "model": [{"tools": [{"tool": "data_catalog", "args": {"dataset": "unit_month_summary"}}]}, {"text": "The catalog lists the columns."}],
            "expect": {"kind": "answer", "model_never_sees": ["twelve monthly headcounts"]},
        }],
    }
    with pytest.raises(AssertionError, match="a model was shown"):
        asyncio.run(play(leaky))


def test_a_case_that_names_the_wrong_tool_sequence_fails():
    wrong = {
        "name": "wrong", "turns": [{
            "say": "For Northwind, which worksites are there?",
            "model": [{"tools": [{"tool": "data_distinct_values", "args": {"dataset": "unit_month_summary", "column": "worksite_id"}}]}, {"text": "These are the worksites."}],
            "expect": {"kind": "answer", "gateway": ["client_resolve", "data_query"]},
        }],
    }
    with pytest.raises(AssertionError, match="wrong turn 1"):
        asyncio.run(play(wrong))
