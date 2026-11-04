"""A figure only the person's rows hold is not a figure the narrator may use; the data tools have no way round the guard. [RM-05, ADR-008, ADR-009]

The narrator writes prose around the platform's blocks. It may not type a figure, and it may name a
fact only by a placeholder the platform renders. Two things need pinning for the data tools:

1. **The person's lane is not allowed context.** A wage that only an employee-level row holds is in
   the table the PERSON is shown and nowhere a model reads: not in the brief, not in the reader's
   allowed numerals, not in what a placeholder may point at. A narration that types it is rejected
   like any typed figure, and one that points a placeholder into the lane is rejected too.
2. **The data tools are ordinary tools to the guard.** `data_catalog`, `data_distinct_values` and
   `data_query` answer with facts like any other tool; their facts are the guard's facts, a figure
   the facts do not hold is rejected, and there is no tool-specific door past the composer.

The rejection never costs the reader anything: the platform's blocks, the person's rows included, are
shown, and the audit records that the narration was refused.
"""
from __future__ import annotations

import ast
import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.compose import OUTSIDE_VIEW, allowed_for, compose_reply, facts_of, model_facts_of, paths_outside_model_view
from app.core.tools import ToolRun
from application.capabilities import catalog
from application.capabilities.lanes import MODEL_ROW_LIMIT
from application.numeric.guard import FactIndex
from data_harness import data_reply
from orch_harness import USER_OID, build_rig

EMPLOYEE_ASK = "Northwind: list the people in the eligibility data with their wages."
EMPLOYEE_CALL = {"tool": "data_query", "args": {"dataset": "employee_eligibility", "select": ["record_token", "total_wages"], "limit": 4}}
AGGREGATE_ASK = "Northwind: how many rows does each method have in the unit month summary?"
AGGREGATE_CALL = {"tool": "data_query", "args": {"dataset": "unit_month_summary", "select": ["method"],
                                                 "measures": [{"column": "*", "agg": "count", "as": "n"}]}}
#: In the person's rows (and so in the table the person is shown) and in no other fact of the result.
ROW_WAGES = ("1.5", "2.5", "3.5", "4.5")
ROW_TOKEN = "record_token-2002-"
APP = Path(__file__).resolve().parents[3] / "channel_orchestrator" / "app"


def ask(narration: str, call: dict, say: str):
    rig = build_rig([{"tools": [call]}, {"text": narration}])
    return asyncio.run(rig.say(say))


def employee_run() -> ToolRun:
    status, envelope = data_reply("data_query", {"client_id": 2002, **EMPLOYEE_CALL["args"]}, USER_OID)
    assert status == 200 and envelope["user_only_facts"] == ["rows"]
    return ToolRun("data_query", {"client_id": 2002}, envelope, label="data_query")


# ----------------------------------------------- the person's lane is not the narrator's context


def test_the_wages_exist_only_in_the_persons_lane():
    run = employee_run()
    held, shown = FactIndex.coerce(facts_of([run])), FactIndex.coerce(model_facts_of([run]))
    for wage in ROW_WAGES:
        assert Decimal(wage) in held.values, "the person's reply can be verified against the rows it shows"
        assert Decimal(wage) not in shown.values, "a model's view of the result does not hold them"
    assert not any(".rows." in path for path in shown.leaves)


def test_the_readers_allowed_numerals_never_include_a_figure_from_the_rows():
    run = employee_run()
    context = allowed_for(EMPLOYEE_ASK, [run])
    assert not {Decimal(w) for w in ROW_WAGES} & context.values
    assert not {Decimal(w) for w in ROW_WAGES} & context.percents


@pytest.mark.parametrize("wage", ROW_WAGES)
def test_a_narration_that_types_a_wage_only_the_rows_hold_is_rejected_and_the_person_still_gets_the_rows(wage):
    reply = ask(f"The highest wage in the list is {wage} dollars.", EMPLOYEE_CALL, EMPLOYEE_ASK)
    assert reply.kind == "answer" and reply.narration_used is False and reply.guard_status == "rejected"
    assert "highest wage" not in reply.text and ROW_TOKEN in reply.text and wage in reply.text, "the table is the person's, the sentence is not"


@pytest.mark.parametrize("path", ["rows.0.total_wages", "rows.3.total_wages", "rows.0.record_token", "rows.1.method"])
def test_a_placeholder_pointing_into_the_persons_lane_is_rejected(path):
    reply = ask("Here is the first one: {{facts.data_query." + path + "}}.", EMPLOYEE_CALL, EMPLOYEE_ASK)
    assert reply.narration_used is False and reply.guard_status == "rejected"
    assert "Here is the first one" not in reply.text and ROW_TOKEN in reply.text


def test_the_rejection_is_audited_as_a_code_never_naming_the_path():
    reply = ask("Top: {{facts.data_query.rows.0.total_wages}}.", EMPLOYEE_CALL, EMPLOYEE_ASK)
    assert reply.guard_status == "rejected"
    composed = compose_reply("", [employee_run()], "Top: {{facts.data_query.rows.0.total_wages}}.")
    assert [v.reason for v in composed.guard.violations] == [OUTSIDE_VIEW]
    assert "rows" not in composed.guard.violations[0].reason and "total_wages" not in composed.guard.violations[0].reason


def test_a_placeholder_for_a_fact_the_model_was_shown_is_still_rendered():
    reply = ask("There are {{facts.data_query.row_count}} rows.", EMPLOYEE_CALL, EMPLOYEE_ASK)
    assert reply.narration_used is True and reply.guard_status == "pass" and "There are 4 rows." in reply.text


def test_the_rule_is_about_the_lane_not_about_rows_an_aggregate_is_narratable():
    reply = ask("The first method has {{facts.data_query.rows.0.n}} rows.", AGGREGATE_CALL, AGGREGATE_ASK)
    assert reply.narration_used is True and reply.guard_status == "pass"


def test_rows_past_the_models_cut_are_not_a_placeholder_target_either():
    rows = [{"method": f"m{i}", "n": i + 1} for i in range(MODEL_ROW_LIMIT + 10)]
    envelope = {"tool": "data_query", "facts": {"rows": rows, "row_count": len(rows)}, "blocks": []}
    run = ToolRun("data_query", {}, envelope, label="q")
    assert paths_outside_model_view("{{facts.q.rows.3.n}}", [run]) == []
    assert paths_outside_model_view(f"{{{{facts.q.rows.{MODEL_ROW_LIMIT + 1}.n}}}}", [run]) == [f"q.rows.{MODEL_ROW_LIMIT + 1}.n"]


def test_a_path_that_does_not_exist_is_still_the_composers_to_reject():
    run = employee_run()
    assert paths_outside_model_view("{{facts.data_query.nothing_here}}", [run]) == []
    composed = compose_reply("", [run], "It is {{facts.data_query.nothing_here}}.")
    assert composed.narration_used is False and composed.guard.status == "rejected"


def test_a_reply_with_no_narration_is_unchanged_and_verifies_its_own_blocks():
    run = employee_run()
    composed = compose_reply("", [run], None)
    assert composed.narration_used is False and composed.blocks_verified and composed.guard.status == "pass"
    assert ROW_TOKEN in composed.text and "2.5" in composed.text


# -------------------------------------- the data tools cannot get a figure past the guard

LOOKUPS = {
    "data_catalog": ({"tool": "data_catalog", "args": {"dataset": "unit_month_summary"}}, "What can I ask about the unit month summary?",
                     "datasets.0.column_count", "20"),
    "data_distinct_values": ({"tool": "data_distinct_values", "args": {"dataset": "unit_month_summary", "column": "worksite_id"}},
                             "Northwind: which worksites are in the unit month summary?", "value_count", "2"),
    "data_query": (AGGREGATE_CALL, AGGREGATE_ASK, "rows.0.n", "2"),
}


@pytest.mark.parametrize("tool", LOOKUPS)
def test_a_figure_a_data_tool_did_not_return_is_rejected(tool):
    call, say, _, _ = LOOKUPS[tool]
    reply = ask("It has 987654 of them.", call, say)
    assert reply.narration_used is False and reply.guard_status == "rejected"


@pytest.mark.parametrize("tool", LOOKUPS)
def test_a_figure_a_data_tool_did_return_is_still_not_the_models_to_type(tool):
    call, say, path, figure = LOOKUPS[tool]
    reply = ask(f"There are {figure} of them.", call, say)
    assert reply.narration_used is False and reply.guard_status == "rejected", "the model may only name it, the platform prints it"


@pytest.mark.parametrize("tool", LOOKUPS)
def test_an_invented_path_on_a_data_tool_is_rejected(tool):
    call, say, _, _ = LOOKUPS[tool]
    reply = ask("It has {{facts." + tool + ".not_a_fact}} of them.", call, say)
    assert reply.narration_used is False and reply.guard_status == "rejected"


@pytest.mark.parametrize("tool", LOOKUPS)
def test_the_one_way_a_data_tool_figure_reaches_the_reader_is_a_placeholder_the_platform_renders(tool):
    call, say, path, figure = LOOKUPS[tool]
    reply = ask("It reports {{facts." + tool + "." + path + "}} in all.", call, say)
    assert reply.narration_used is True and reply.guard_status == "pass" and f"It reports {figure} in all." in reply.text


@pytest.mark.parametrize("tool", LOOKUPS)
def test_a_data_tools_facts_are_the_guards_facts(tool):
    call, say, path, figure = LOOKUPS[tool]
    args = {k: v for k, v in call["args"].items()}
    status, envelope = data_reply(tool, {**({"client_id": 2002} if tool != "data_catalog" else {}), **args}, USER_OID)
    run = ToolRun(tool, args, envelope, label=tool)
    index = FactIndex.coerce(facts_of([run]))
    assert status == 200 and f"{tool}.{path}" in index.leaves and Decimal(figure) in index.values
    assert Decimal("987654") not in index.values


# ---------------------------------------------------------------------- structure


def test_the_composer_is_reached_only_through_compose_reply():
    """A reply is composed in one function. Another caller of `compose` would be a second door past the narration rules."""
    callers = []
    for path in sorted(APP.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "compose":
                callers.append(path.name)
    assert callers == ["compose.py"], callers


def test_every_data_tool_is_an_ordinary_read_the_guard_sees():
    """Not gateway-local and not internal: a data tool's result is recorded by the ledger and composed by the one composer."""
    data_tools = {"data_catalog", "data_query", "data_distinct_values"}
    specs = {spec.name: spec for spec in catalog.CATALOG}
    assert data_tools <= set(specs)
    for name in data_tools:
        assert specs[name].kind == catalog.READ and not {catalog.GATEWAY_LOCAL, catalog.INTERNAL} & set(specs[name].tags)
    from app.core.toolset import model_tools

    assert data_tools <= set(model_tools())
