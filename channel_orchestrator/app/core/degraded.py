"""The degraded planners: what answers when no tool-calling model can. [CH-08, RM-10a]

The tool-calling Agent (`planner.Planner`) is THE planner for an open-ended question. These two exist for the
cases where it cannot run, behind one small interface, and for nothing else:

- **json** (`DegradedPlanner` for a provider without tool calling, `AI_GATEWAY_SUPPORTS_TOOLS=false`): the
  model returns `{"tools": [...]}`, a plan the runner checks against the tools it may name; a second call writes
  the narration. An invented tool name is dropped, never run.
- **keywords** (no model configured, the injection screen fired, or the model layer failed): the platform's own
  keyword table picks the tools and nothing narrates. It cannot be talked into anything, and it is what answers
  when no model is reachable.

Both run their tools through `ToolRunner.run`, which is the same rules the agent's loop applies (the budget, the
refusal of a commit, the client, the year and the method, the schema, the ledger), and both end in the same
composition (`Planned.composed_for`) and the same narrator brief (`compose.narration_brief`) as the agent path.
Neither is a place to add a capability: a question the platform cannot answer without a tool-calling model is
answered by the keyword table or not at all.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from app.core.compose import LOOKUP_TOOLS, narration_brief
from app.core.model_access import ModelAccess
from app.core.planned import Planned
from app.core.prompts import PLAN_JSON, narrator_instructions, tool_catalogue
from app.core.tools import ToolRunner
from application.ai.safety.untrusted import UntrustedText
from application.capabilities.catalog_intents import CHAT_INTENT_TOOL
from application.chat_keywords import keyword_intents
from domain.ai import ChatMessage

JSON, KEYWORDS = "json", "keywords"


class DegradedPlanner(Protocol):
    """A planner that needs no tool-calling model. It runs the turn's tools and may leave a narration on `planned`."""

    mode: str

    async def plan(self, runner: ToolRunner, planned: Planned) -> Planned: ...


def plan_steps(raw: str, limit: int) -> list[dict[str, Any]]:
    """The tools a JSON plan names, in order, at most `limit`, arguments as an object.

    Names are NOT filtered here: the runner refuses anything a model may not call and
    records the attempt, which is the one place that decision is made and logged.
    """
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        document = json.loads(raw[start:end])
    except ValueError:
        return []
    items = document.get("tools") if isinstance(document, dict) else None
    steps = []
    for item in items if isinstance(items, list) else []:
        name = item.get("tool") if isinstance(item, dict) else item
        if isinstance(name, str):
            args = item.get("args") if isinstance(item, dict) and isinstance(item.get("args"), dict) else {}
            steps.append({"tool": name, "args": args})
    return steps[:limit]


class JsonPlanner:
    """A model that cannot call tools names them as JSON, and writes the connective sentence in a second call."""

    mode = JSON

    def __init__(self, chain: ModelAccess) -> None:
        self._chain = chain

    async def plan(self, runner: ToolRunner, planned: Planned) -> Planned:
        system = f"{PLAN_JSON}\nTOOLS:\n{tool_catalogue()}"
        asked = [ChatMessage("system", system), ChatMessage("user", UntrustedText(runner.question, "reader question").fenced())]
        looked_up = await self._round(asked, runner, planned)
        if looked_up and all(run.name in LOOKUP_TOOLS for run in runner.runs):
            # A plan made only of lookups cannot name a column it has not read: show the model what they returned, once.
            asked.append(ChatMessage("user", "LOOKUP RESULTS (the data's own names; use only these):\n" + json.dumps(looked_up)))
            await self._round(asked, runner, planned)
        if runner.runs and not runner.clarify:
            planned.narrate(await self._narrate(runner, planned))
        return planned

    async def _round(self, asked: list[ChatMessage], runner: ToolRunner, planned: Planned) -> dict[str, Any]:
        """One planning call and the tools it names; the `result` of each lookup tool that answered, by tool."""
        planned.trace.sent(asked)
        turn = await self._chain.complete(asked)
        planned.trace.took(turn)
        looked_up: dict[str, Any] = {}
        for step in plan_steps(turn.text, runner.max_calls):
            answer = await runner.run(step["tool"], step["args"])
            if answer.get("ok") and "result" in answer:
                looked_up[step["tool"]] = answer["result"]
        return looked_up

    async def _narrate(self, runner: ToolRunner, planned: Planned) -> str:
        text, _ = narrator_instructions()
        asked = [ChatMessage("system", text), ChatMessage("user", "JSON:\n" + json.dumps(narration_brief(runner.question, runner.runs, fenced=True)))]
        planned.trace.sent(asked)
        turn = await self._chain.complete(asked, prefer=planned.trace.last.provider if planned.trace.last else None)
        planned.trace.took(turn)
        return turn.text


class KeywordPlanner:
    """No model: the platform's keyword table picks the tools, and nothing narrates."""

    mode = KEYWORDS

    async def plan(self, runner: ToolRunner, planned: Planned) -> Planned:
        tools: list[str] = []
        for intent in keyword_intents(runner.question):
            tool = CHAT_INTENT_TOOL.get(intent)
            if tool and tool not in tools:
                tools.append(tool)
        for tool in tools[: runner.max_calls]:
            await runner.run(tool, {})
        planned.mode = self.mode
        return planned
