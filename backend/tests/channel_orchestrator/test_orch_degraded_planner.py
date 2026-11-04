"""RM-10a: the Agent is the planner; json and keywords are one small, documented degraded path. [CH-08, RM-10a]

What is pinned here is the SHAPE the collapse left: one interface for the degraded planners, one dispatch rule in
`Planner`, one place a reply is composed, one narrator brief, one trace. The behaviour of each mode is the golden
cases' (`golden/fallback.json`, `planning.json`) and was not edited.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

from app.core.compose import compose_reply, facts_of, narration_brief
from app.core.degraded import JSON, KEYWORDS, DegradedPlanner, JsonPlanner, KeywordPlanner, plan_steps
from app.core.maf_chat import ModelTrace
from app.core.models import ModelChain, ModelTurn, Provider
from app.core.planned import Planned
from app.core.planner import TOOLS, Planner
from app.core.state import ConversationState
from app.core.tools import ToolRun, ToolRunner
from application.composer import narrator_brief
from domain.ai import ChatMessage
from orch_harness import FakeClock, FakeGateway, ScriptedChat, build_rig, identity

APP = Path(__file__).resolve().parents[3] / "channel_orchestrator" / "app"


class Access:
    """A `ModelAccess` that says what it is and refuses to be asked anything."""

    def __init__(self, *, configured: bool = True, tools: bool = True, flagged: bool = False) -> None:
        self.configured, self.tools_available, self._flagged = configured, tools, flagged

    def screen(self, text: str) -> bool:
        return self._flagged

    async def complete(self, messages, tools=(), *, prefer=None) -> ModelTurn:
        raise AssertionError("the planner under test must not call a model itself")


class Recorder:
    """A degraded planner that records that it was asked, and what mode it left."""

    def __init__(self, mode: str, *, runs: bool = False) -> None:
        self.mode, self.asked, self._runs = mode, 0, runs

    async def plan(self, runner: ToolRunner, planned: Planned) -> Planned:
        self.asked += 1
        planned.mode = self.mode
        if self._runs:
            runner.runs.append(ToolRun("client_trend", {}, {}, "client_trend"))
        return planned


def runner_for(question: str = "How has Cascade trended?") -> ToolRunner:
    return ToolRunner(FakeGateway().client(), identity(), ConversationState(), question, 6, 300, FakeClock())


def plan(planner: Planner, question: str = "How has Cascade trended?"):
    return asyncio.run(planner.plan(runner_for(question)))


# ------------------------------------------------------------------ the interface


def test_both_degraded_planners_satisfy_the_one_interface():
    for planner, mode in ((JsonPlanner(Access()), JSON), (KeywordPlanner(), KEYWORDS)):
        assert planner.mode == mode and callable(planner.plan)
    declared = set(DegradedPlanner.__annotations__) | {n for n in vars(DegradedPlanner) if n == "plan"}
    assert declared == {"mode", "plan"}, "the interface stays small"


def test_the_agent_plans_when_a_tool_calling_model_is_reachable_and_no_degraded_planner_is_asked():
    json_planner, keywords = Recorder(JSON), Recorder(KEYWORDS)
    chat = ScriptedChat([{"text": "no tools needed"}])
    chain = ModelChain([Provider("gateway", chat, "m", True)], egress_policy="allow_all", timeout_seconds=5.0)
    planned = plan(Planner(chain, degraded={JSON: json_planner, KEYWORDS: keywords}))
    assert planned.mode == TOOLS and planned.model_used and not planned.degraded
    assert json_planner.asked == 0 and keywords.asked == 0


def test_a_model_without_tool_calling_is_the_json_planner_and_no_model_is_the_keyword_planner():
    json_planner, keywords = Recorder(JSON), Recorder(KEYWORDS)
    degraded = {JSON: json_planner, KEYWORDS: keywords}
    assert plan(Planner(Access(tools=False), degraded=degraded)).mode == JSON
    assert (json_planner.asked, keywords.asked) == (1, 0)
    assert plan(Planner(Access(configured=False), degraded=degraded)).mode == KEYWORDS
    assert (json_planner.asked, keywords.asked) == (1, 1)


def test_a_message_the_injection_screen_flags_reaches_no_model_and_is_the_keyword_planners():
    keywords = Recorder(KEYWORDS)
    planned = plan(Planner(Access(flagged=True), degraded={JSON: Recorder(JSON), KEYWORDS: keywords}))
    assert planned.mode == KEYWORDS and not planned.model_used and keywords.asked == 1


def test_a_model_layer_that_fails_before_any_tool_ran_falls_to_the_keywords_and_says_so():
    class Broken(Recorder):
        async def plan(self, runner, planned):
            raise RuntimeError("the model layer is down")

    keywords = Recorder(KEYWORDS)
    planned = plan(Planner(Access(tools=False), degraded={JSON: Broken(JSON), KEYWORDS: keywords}))
    assert keywords.asked == 1 and planned.degraded and planned.mode == KEYWORDS and planned.narration is None


def test_a_model_layer_that_fails_after_tools_ran_keeps_what_they_returned():
    class HalfWay(Recorder):
        async def plan(self, runner, planned):
            runner.runs.append(ToolRun("client_trend", {}, {}, "client_trend"))
            raise RuntimeError("the narration call failed")

    keywords = Recorder(KEYWORDS)
    planned = plan(Planner(Access(tools=False), degraded={JSON: HalfWay(JSON), KEYWORDS: keywords}))
    assert keywords.asked == 0 and planned.degraded and planned.mode == JSON


def test_the_real_degraded_planners_are_the_default_and_answer_through_the_runners_rules():
    rig = build_rig(supports_tools=False, script=[{"text": json.dumps({"tools": [{"tool": "client_trend", "args": {}}]})}, {"text": "A trend."}])
    reply = asyncio.run(rig.say("How has Cascade trended?"))
    assert reply.mode == JSON and reply.kind == "answer"
    assert rig.gateway.tools_called() == ["client_resolve", "client_trend"]
    none = build_rig(configured=False)
    assert asyncio.run(none.say("Brief me on Cascade")).mode == KEYWORDS and none.chat.seen == []


# --------------------------------------------------------------- one plan reader


def test_a_json_plan_names_tools_in_order_up_to_the_limit_and_filters_nothing():
    raw = 'prose {"tools": [{"tool": "a", "args": {"x": 1}}, "b", {"tool": "c"}, {"nope": 1}, 7]} more'
    assert plan_steps(raw, 2) == [{"tool": "a", "args": {"x": 1}}, {"tool": "b", "args": {}}]
    assert plan_steps(raw, 9)[2] == {"tool": "c", "args": {}}
    assert plan_steps("no json here", 3) == [] and plan_steps('{"tools": "x"}', 3) == []


# ----------------------------------------------------------- one compose path


def run_of(name: str = "client_trend") -> ToolRun:
    body = {"facts": {"years": [{"annual_average": "410.13"}]}, "blocks": [{"kind": "paragraph", "text": "The trend."}]}
    return ToolRun(name, {}, body, name)


def test_a_reply_is_composed_once_from_the_turns_results_and_again_only_after_a_new_narration():
    runner = runner_for()
    runner.runs.append(run_of())
    planned = Planned("tools", hosts=("example.test",))
    first = planned.composed_for(runner)
    assert planned.composed_for(runner) is first, "composed once"
    assert first.text == compose_reply(runner.question, runner.runs, None, ("example.test",)).text
    planned.narrate("Some words without a figure.")
    assert planned.composed is None, "a new narration invalidates what was composed"
    assert planned.composed_for(runner) is not first


def test_a_failed_model_layer_forgets_its_narration_and_marks_the_answer_as_the_platforms_own():
    planned = Planned("tools", narration="x", model_used=True)
    planned.fall_back()
    assert planned.degraded and planned.narration is None and planned.composed is None


def test_compose_reply_is_called_by_the_composition_point_and_the_commit_path_and_nothing_else():
    callers = sorted({
        p.name for p in APP.glob("core/*.py") for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "compose_reply"
    })
    assert callers == ["planned.py", "writes.py"], f"a second place composes a reply: {callers}"


# --------------------------------------------------------- one narrator brief


def test_the_brief_every_path_hands_a_model_names_facts_with_placeholders_and_no_value():
    runs = [run_of()]
    brief = narration_brief("Q?", runs)
    assert all(entry["placeholder"].startswith("{{facts.client_trend.") for entry in brief["fact_paths"])
    assert "410.13" not in json.dumps(brief)
    plain = narrator_brief("Q?", ["client_trend"], {"client_trend": runs[0].model_facts}, notes=[])
    assert [e["path"] for e in brief["fact_paths"]] == [e["path"] for e in plain["fact_paths"]]
    assert narration_brief("Q?", runs, fenced=True)["question"] != brief["question"], "the single-call path marks the reader's words"
    assert "Q?" in narration_brief("Q?", runs, fenced=True)["question"]


def test_the_brief_is_built_in_one_function_not_in_each_planner():
    users = sorted({
        p.name for p in APP.glob("core/*.py") for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "narrator_brief"
    })
    assert users == ["compose.py"], users


# ------------------------------------------------------------------ one trace


def test_every_model_call_is_noted_the_same_way_whichever_planner_made_it():
    trace = ModelTrace()
    messages = [ChatMessage("system", "s"), ChatMessage("user", "u")]
    trace.sent(messages)
    turn = ModelTurn("hello", (), "gateway", "m", ("gateway",))
    trace.took(turn)
    assert trace.prompt_parts == ["s\nu"] and trace.last is turn
    touching = sorted({
        p.name for p in APP.glob("core/*.py") for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(n, ast.Attribute) and n.attr == "prompt_parts"
    })
    assert touching == ["audit.py", "maf_chat.py", "maf_foundry_client.py"], f"write to the trace through ModelTrace.sent/took: {touching}"


def test_the_facts_a_reply_is_checked_against_are_the_runs_own():
    runner = runner_for()
    runner.runs.append(run_of())
    assert facts_of(runner.runs) == {"client_trend": run_of().facts}
