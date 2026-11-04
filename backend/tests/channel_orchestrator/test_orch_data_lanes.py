"""What a model is shown of a data result: names and aggregates, never a person's row. [CH-16d, ADR-009]

The product's egress invariant is that employee identifiers and record tokens never enter a prompt. The
data tools can return exactly such rows, so the invariant is re-asserted for them, in both planner modes,
against the real capabilities' own envelopes (`data_harness`): the person's reply carries the rows, every
byte a model is sent does not, and the one declared exception (the catalog and the distinct values, which
describe the shape of the data) is shown to be exactly that.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core.compose import blocks_of, facts_of, model_facts_of
from app.core.tools import ToolRun
from application.ai.egress import identifier_findings
from application.capabilities import lanes
from orch_harness import build_rig

EMPLOYEE_ASK = "Northwind: list the people in the eligibility data with their method."
EMPLOYEE_CALL = {"tool": "data_query", "args": {"dataset": "employee_eligibility", "select": ["record_token", "method"], "limit": 3}}
AGGREGATE_ASK = "Northwind: how many rows does each method have in the unit month summary?"
AGGREGATE_CALL = {"tool": "data_query", "args": {"dataset": "unit_month_summary", "select": ["method"],
                                                 "measures": [{"column": "*", "agg": "count", "as": "n"}]}}
ROW_VALUE = "record_token-2002-"  # the shape of a row value in the shared fixture, for client 2002


def sent_to_models(rig) -> str:
    """Every byte of every message any model was sent in the turn."""
    return "\n".join(m.content or "" for seen in rig.chat.seen for m in seen["messages"])


def ask(script, say, **rig_kwargs):
    rig = build_rig(script, **rig_kwargs)
    return rig, asyncio.run(rig.say(say))


@pytest.mark.parametrize("tools", [True, False])
def test_the_person_gets_the_rows_and_no_model_is_sent_one(tools):
    script = ([{"tools": [EMPLOYEE_CALL]}, {"text": "Here are the people."}] if tools
              else [{"text": json.dumps({"tools": [EMPLOYEE_CALL]})}, {"text": "Here are the people."}])
    rig, reply = ask(script, EMPLOYEE_ASK, supports_tools=tools)
    assert reply.kind == "answer" and ROW_VALUE in reply.text, "the person's lane is in the reply"
    seen = sent_to_models(rig)
    assert seen and ROW_VALUE not in seen and "record_token-" not in seen.replace("record_token", "")
    assert identifier_findings(seen) == []


def test_what_a_model_is_told_about_the_rows_is_the_count_and_the_column_names():
    rig, reply = ask([{"tools": [EMPLOYEE_CALL]}, {"text": "Here are the people."}], EMPLOYEE_ASK)
    tool_messages = [m.content for seen in rig.chat.seen for m in seen["messages"] if m.role == "tool"]
    answer = json.loads(next(t for t in tool_messages if '"data_query"' in t))
    assert answer["ok"] is True and answer["tool"] == "data_query" and "result" not in answer
    paths = [p["path"] for p in answer["fact_paths"]]
    assert "data_query.row_count" in paths and not any(".rows." in p for p in paths)


def test_an_aggregate_is_shown_to_the_model_by_name_so_it_can_be_narrated():
    rig, reply = ask([{"tools": [AGGREGATE_CALL]}, {"text": "The first method has {{facts.data_query.rows.0.n}} rows."}], AGGREGATE_ASK)
    assert reply.guard_status == "pass" and reply.narration_used and "min_max" in reply.text
    tool_message = next(m.content for seen in rig.chat.seen for m in seen["messages"] if m.role == "tool")
    assert "data_query.rows.0.n" in tool_message, "an aggregate's rows are narratable by placeholder"
    assert "min_max" not in tool_message, "names, never values"


def test_the_catalog_and_the_distinct_values_are_the_declared_exception_and_nothing_else_is():
    script = [{"tools": [{"tool": "data_catalog", "args": {"dataset": "unit_month_summary"}},
                         {"tool": "data_distinct_values", "args": {"dataset": "unit_month_summary", "column": "worksite_id"}}]},
              {"text": "Here is what exists."}]
    rig, reply = ask(script, "Northwind: what worksites are in the unit month summary?")
    by_tool = {json.loads(m.content)["tool"]: json.loads(m.content) for seen in rig.chat.seen for m in seen["messages"]
               if m.role == "tool" and m.content.startswith("{")}
    assert {"worksite_id", "tax_year"} <= {c["name"] for c in by_tool["data_catalog"]["result"]["datasets"][0]["columns"]}
    assert "worksite_id-2002-0" in json.dumps(by_tool["data_distinct_values"]["result"])
    assert all(p["format"] != "text" for p in by_tool["data_catalog"]["fact_paths"])
    assert identifier_findings(sent_to_models(rig)) == []


def test_the_catalog_blocks_are_left_out_of_a_reply_that_something_else_answered():
    script = [{"tools": [{"tool": "data_catalog", "args": {"dataset": "unit_month_summary"}}, AGGREGATE_CALL]}, {"text": "Here."}]
    _, reply = ask(script, AGGREGATE_ASK)
    assert "Query result" in reply.text and "Queryable data" not in reply.text


def test_a_catalog_question_is_answered_with_the_catalog():
    _, reply = ask([{"tools": [{"tool": "data_catalog", "args": {}}]}, {"text": "This is what I can look at."}], "What data can you look at?")
    assert "Queryable data" in reply.text and "unit_month_summary" in reply.text


# ------------------------------------------------------------------ the projection itself


def run_of(envelope: dict, name: str = "data_query") -> ToolRun:
    return ToolRun(name, {}, envelope, label=name)


def test_the_projection_the_model_reads_drops_the_persons_lane_and_the_reply_keeps_it():
    from data_harness import data_reply
    from orch_harness import USER_OID

    status, envelope = data_reply("data_query", {"client_id": 2002, **EMPLOYEE_CALL["args"]}, USER_OID)
    assert status == 200 and lanes.has_user_lane(envelope)
    run = run_of(envelope)
    assert "rows" in facts_of([run])["data_query"] and "rows" not in model_facts_of([run])["data_query"]
    assert "rows" not in run.model_facts and ROW_VALUE in json.dumps(run.facts)
    assert any(b.audience == "user" for b in blocks_of([run])), "the composer still has the person's table"
    assert ROW_VALUE not in json.dumps(model_facts_of([run]))


def test_every_field_of_every_data_tool_envelope_is_either_the_persons_or_free_of_row_values():
    from data_harness import data_reply
    from orch_harness import USER_OID

    for tool, args in (("data_query", EMPLOYEE_CALL["args"]), ("data_query", AGGREGATE_CALL["args"]),
                       ("data_catalog", {}), ("data_distinct_values", {"dataset": "unit_year_master", "column": "worksite_id"})):
        needs = {"client_id": 2002} if tool != "data_catalog" else {}
        status, envelope = data_reply(tool, {**needs, **args}, USER_OID)
        assert status == 200, tool
        visible = json.dumps({"facts": lanes.model_facts(envelope), "blocks": lanes.model_blocks(envelope)})
        if envelope["facts"].get("audience") == "user":
            assert ROW_VALUE not in visible and "record_token-" not in visible.replace('"record_token"', "")


def test_a_model_cannot_choose_a_data_tool_that_writes_or_a_commit_and_the_data_tools_are_named_for_it():
    from app.core.tools import model_tools

    names = set(model_tools())
    assert {"data_catalog", "data_query", "data_distinct_values"} <= names
