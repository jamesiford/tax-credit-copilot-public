"""The tool rules are MAF middleware that runs inside the model's own loop, in a fixed order. [RM-08]

Before RM-08 `ToolRunner` held every rule and the framework only carried a closure to it. These tests go
through a real `Agent` (a scripted model, the real gateway client over an in-process gateway) and prove that
each rule now fires from the framework's middleware, that the order is the one the guarantees need, that the
degraded modes reach the very same objects, and that what is left of `ToolRunner` is the turn's state.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

from agent_framework import FunctionMiddleware

from app.core import maf_tool_call, maf_tool_rules
from app.core.maf_agent import ModelTrace, build_agent, function_tools
from app.core.models import ModelChain, Provider
from app.core.state import ConversationState
from app.core.tools import ToolRunner
from orch_harness import FakeClock, FakeGateway, ScriptedChat, identity

APP = Path(__file__).resolve().parents[3] / "channel_orchestrator" / "app" / "core"
ORDER = ["Budget", "RefuseUnlisted", "ClientFromReader", "YearAndMethodFromReader", "SchemaCheck", "CallAndCapture"]


def agent_for(script, question="Cascade trend 2023", max_calls=6, gateway=None):
    chat = ScriptedChat(script)
    chain = ModelChain([Provider("gateway", chat, "m", True)], egress_policy="allow_all", timeout_seconds=5.0)
    gateway = gateway or FakeGateway()
    runner = ToolRunner(gateway.client(), identity(), ConversationState(), question, max_calls, 300, FakeClock())
    seen: list[str] = []
    return build_agent(chain, runner, ModelTrace(), "be good", lambda raw: seen.append(raw) or "COMPOSED"), runner, gateway, chat


def tool_messages(chat) -> list[str]:
    """What the model was told about each tool it called (the tool-role messages of its last request)."""
    return [m.content for m in chat.seen[-1]["messages"] if m.role == "tool"]


def call(tool, **args):
    return {"tool": tool, "args": args}


def test_the_rules_run_in_the_order_the_guarantees_need_inside_the_models_loop(monkeypatch):
    fired: list[str] = []
    for cls in (*{type(r) for r in maf_tool_rules.tool_rules()}, maf_tool_call.CallAndCapture):
        original = cls.process

        async def traced(self, context, call_next, _name=cls.__name__, _original=original):
            fired.append(_name)
            await _original(self, context, call_next)

        monkeypatch.setattr(cls, "process", traced)
    agent, *_ = agent_for([{"tools": [call("client_trend")]}, {"text": "done"}])
    asyncio.run(agent.run("How has Cascade trended?"))
    assert fired == ORDER
    assert [type(r).__name__ for r in maf_tool_rules.tool_rules()] + ["CallAndCapture"] == ORDER


def test_every_rule_is_framework_middleware_built_once_and_carrying_no_turn():
    rules = [*maf_tool_rules.tool_rules(), maf_tool_call.CallAndCapture()]
    assert all(isinstance(r, FunctionMiddleware) for r in rules)
    assert all(vars(r) == {} for r in rules), "a rule that holds state would be shared between two people's turns"


def test_the_budget_is_counted_by_the_first_rule_and_a_call_over_it_never_reaches_the_gateway():
    agent, runner, gateway, chat = agent_for([{"tools": [call("client_trend"), call("client_situation")]}, {"text": "x"}], max_calls=1)
    asyncio.run(agent.run("How has Cascade trended?"))
    answers = [json.loads(m) for m in tool_messages(chat)]
    assert answers[0]["ok"] is True and answers[1]["error"] == "tool_budget"
    assert gateway.tools_called() == ["client_resolve", "client_trend"] and runner.calls == 1


def test_a_commit_the_model_asks_for_is_recorded_and_refused_and_nothing_is_called():
    agent, runner, gateway, chat = agent_for([{"tools": [call("engagement_set_commit", confirmation_token="t")]}, {"text": "x"}])
    asyncio.run(agent.run("Mark Cascade as in scope"))
    assert runner.refused == ["engagement_set_commit"] and gateway.tools_called() == []
    assert not {t.name for t in function_tools() if t.name.endswith("_commit")}
    assert "not found" in tool_messages(chat)[0]


def test_an_invented_tool_is_recorded_too_and_a_listed_one_is_not():
    agent, runner, gateway, _ = agent_for([{"tools": [call("trend_analysis"), call("client_trend")]}, {"text": "x"}])
    asyncio.run(agent.run("How has Cascade trended?"))
    assert runner.refused == ["trend_analysis"] and "client_trend" in gateway.tools_called()


def test_the_client_the_model_passes_is_written_over_by_the_readers():
    agent, runner, gateway, _ = agent_for([{"tools": [call("client_trend", client_id=2003)]}, {"text": "x"}], question="How has Cascade trended?")
    asyncio.run(agent.run("How has Cascade trended?"))
    assert [c.args for c in gateway.calls if c.tool == "client_trend"] == [{"client_id": 2001}]


def test_a_question_back_stops_the_call_and_the_model_is_told_to_wait():
    agent, runner, gateway, chat = agent_for([{"tools": [call("client_eligibility")]}, {"text": "x"}], question="Cascade eligibility")
    asyncio.run(agent.run("Cascade eligibility"))
    assert json.loads(tool_messages(chat)[0])["error"] == "needs_year" and runner.clarify.kind == "year"
    assert "client_eligibility" not in gateway.tools_called()


def test_a_year_the_reader_did_not_say_is_replaced_and_the_method_defaults_to_both_runs():
    agent, runner, gateway, _ = agent_for([{"tools": [call("client_eligibility", tax_year=1999)]}, {"text": "x"}], question="Cascade 2023")
    asyncio.run(agent.run("Cascade 2023"))
    sent = [c.args for c in gateway.calls if c.tool == "client_eligibility"]
    assert [(a["tax_year"], a["method"]) for a in sent] == [(2023, "min_max"), (2023, "pay_period")]
    assert [r.label for r in runner.runs] == ["client_eligibility_min_max", "client_eligibility_pay_period"] and runner.calls == 2


def test_the_schema_check_stops_what_the_catalog_would_refuse_and_records_it():
    agent, runner, gateway, chat = agent_for([{"tools": [call("client_trend", colour="red")]}, {"text": "x"}])
    asyncio.run(agent.run("How has Cascade trended?"))
    assert json.loads(tool_messages(chat)[0])["error"] == "invalid_arguments"
    assert [p.code for p in runner.problems] == ["invalid_arguments"] and "client_trend" not in gateway.tools_called()


def test_a_prepared_changes_token_is_held_by_the_turn_and_never_in_what_the_model_reads():
    agent, runner, gateway, chat = agent_for(
        [{"tools": [call("engagement_set_prepare", program_code="GA_JTC", scope="in_scope")]}, {"text": "x"}], question="Mark Cascade's GA_JTC as in scope",
    )
    asyncio.run(agent.run("Mark Cascade's GA_JTC as in scope"))
    assert runner.pending is not None and runner.pending.token == "tok-1"
    assert "tok-1" not in " ".join(tool_messages(chat)) and "confirmation" not in runner.runs[0].facts


def test_the_degraded_modes_run_the_same_middleware_not_a_copy_of_it(monkeypatch):
    fired: list[str] = []
    original = maf_tool_rules.Budget.process

    async def traced(self, context, call_next):
        fired.append("Budget")
        await original(self, context, call_next)

    monkeypatch.setattr(maf_tool_rules.Budget, "process", traced)
    gateway = FakeGateway()
    runner = ToolRunner(gateway.client(), identity(), ConversationState(), "Cascade trend", 6, 300, FakeClock())
    assert asyncio.run(runner.run("client_trend", {}))["ok"] is True
    assert fired == ["Budget"] and gateway.tools_called() == ["client_resolve", "client_trend"]


def test_a_name_a_model_may_not_call_is_refused_before_any_rule_in_the_degraded_modes_too():
    gateway = FakeGateway()
    runner = ToolRunner(gateway.client(), identity(), ConversationState(), "Cascade", 1, 300, FakeClock())
    asyncio.run(runner.run("client_trend", {}))
    answer = asyncio.run(runner.run("engagement_set_commit", {}))
    assert answer["error"] == "unknown_tool" and runner.refused == ["engagement_set_commit"], "even with the budget spent"


def test_what_is_left_of_the_tool_runner_is_the_turns_state_not_its_rules():
    names = {n for n in dir(ToolRunner) if not n.startswith("__")}
    assert not names & {"_arguments", "_year", "_years", "_method", "_scenario", "_tax_years", "_both_methods", "_call", "_label", "_hold"}
    source = (APP / "tools.py").read_text(encoding="utf-8")
    assert "jsonschema" not in source and "ReaderWords" not in source and "first_schema_problem(" not in source


def test_each_rule_is_written_once_and_only_the_framework_layer_calls_it():
    users = {p.name for p in APP.glob("*.py") if "ReaderWords" in ast.dump(ast.parse(p.read_text(encoding="utf-8")))}
    assert users == {"maf_tool_rules.py", "reader_arguments.py"}
    callers = {p.name for p in APP.glob("*.py") if "first_schema_problem" in p.read_text(encoding="utf-8").replace("def first_schema_problem", "")}
    assert callers <= {"maf_tool_rules.py", "toolset.py", "tools.py"}, callers
