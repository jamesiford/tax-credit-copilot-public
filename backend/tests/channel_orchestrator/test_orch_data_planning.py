"""What the planner is told about the data tools, and how JSON mode reads a lookup before it plans a query. [CH-16e]

The model's only guides to a tool are its description and the planner's instructions. These tests hold
them to the decision rule (fixed engine tools first, the catalog before a query, distinct values to
resolve a name, no invented column), so a later edit cannot quietly blur it. The JSON-planning round
trip is run end to end over the real data capabilities.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core import prompts
from app.core.tools import model_tools
from orch_harness import build_rig

PLAN_CATALOG = {"tools": [{"tool": "data_catalog", "args": {"dataset": "unit_month_summary"}}]}
PLAN_QUERY = {"tools": [{"tool": "data_query", "args": {
    "dataset": "unit_month_summary", "select": ["method"], "measures": [{"column": "*", "agg": "count", "as": "rows_per_method"}]}}]}
ASK = "For Northwind, how many rows does each method have in the unit month summary?"


def flat(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("instruction", [prompts.PLANNER, prompts.PLAN_JSON])
def test_the_planner_instructions_carry_the_decision_rule(instruction):
    text = flat(instruction)
    for must in ("`data_catalog`", "`data_query`", "`data_distinct_values`", "Never invent a column", "fixed engine tools"):
        assert must.lower() in text.lower(), must


def test_the_planner_orders_the_tools_and_names_the_authority():
    text = flat(prompts.PLANNER)
    for must in ("come first", "authoritative", "descriptive or comparative", "A \"why\" question takes the fixed tool first",
                 "the data has nothing for it", "Name every measure with `as`", "another client, or about several"):
        assert must in text, must


def test_the_data_tool_descriptions_tell_the_model_when_and_how():
    query, distinct, catalog = (flat(model_tools()[n].description) for n in ("data_query", "data_distinct_values", "data_catalog"))
    assert "needs a client" in query and "descriptive or comparative" in query and "`as`" in query and "never an invented column" in query
    assert "resolve a name the reader gave" in distinct
    assert "Needs no client" in catalog and "if the catalog has no column for the question, say so" in catalog


def test_the_json_catalogue_and_the_tool_list_carry_the_same_descriptions():
    catalogue = prompts.tool_catalogue()
    for name in ("data_catalog", "data_query", "data_distinct_values"):
        assert f"- {name}: {model_tools()[name].description}" in catalogue


def play(script: list[dict], say: str = ASK):
    rig = build_rig(script, supports_tools=False)
    return rig, asyncio.run(rig.say(say))


def test_json_mode_reads_the_catalog_then_plans_the_query_it_was_shown():
    rig, reply = play([
        {"text": json.dumps(PLAN_CATALOG)}, {"text": json.dumps(PLAN_QUERY)},
        {"text": "The first method has {{facts.data_query.rows.0.rows_per_method|count}} rows."},
    ])
    assert reply.kind == "answer" and reply.mode == "json" and reply.guard_status == "pass", reply.text
    assert [c.tool for c in rig.gateway.calls] == ["data_catalog", "client_resolve", "data_query"]
    second = "\n".join(m.content for m in rig.chat.seen[1]["messages"])
    assert "LOOKUP RESULTS" in second and "unit_month_summary" in second and "worksite_id" in second
    assert "Source: warehouse tcc_gold.unit_month_summary" in reply.text and "rows_per_method" in reply.text


def test_json_mode_asks_again_only_once_and_only_after_lookups():
    rig, reply = play([{"text": json.dumps(PLAN_CATALOG)}, {"text": json.dumps(PLAN_CATALOG)}, {"text": "The catalog is below."}])
    assert reply.kind == "answer"
    assert len(rig.chat.seen) == 3, "plan, plan again, narrate: never a third planning call"


def test_json_mode_does_not_ask_again_when_the_plan_already_holds_a_query():
    both = {"tools": [*PLAN_CATALOG["tools"], *PLAN_QUERY["tools"]]}
    rig, reply = play([{"text": json.dumps(both)}, {"text": "Here are the counts."}])
    assert reply.kind == "answer" and len(rig.chat.seen) == 2
    assert [c.tool for c in rig.gateway.calls] == ["data_catalog", "client_resolve", "data_query"]


def test_json_mode_with_no_lookup_asks_nothing_more():
    rig, reply = play([{"text": json.dumps({"tools": [{"tool": "client_trend", "args": {}}]})}, {"text": "The table shows each year."}],
                      "How has Northwind trended?")
    assert reply.kind == "answer" and len(rig.chat.seen) == 2
