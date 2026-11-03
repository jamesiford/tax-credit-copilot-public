"""Deciding which tools run, and getting a narration around the results. [CH-08]

Three modes, one outcome. In every mode the model (if there is one) chooses WHICH
deterministic tool runs and may write the connective sentence; the tools' facts are the only
source of a figure, and `ToolRunner` enforces whose data it is.

- **tools** (a provider offers tool calling): an MAF `Agent` drives the model's tool calls
  against this turn's `ToolRunner`; its output is replaced by the composed reply.
- **json** (`AI_GATEWAY_SUPPORTS_TOOLS=false`): the model returns `{"tools": [...]}`, a plan
  validated against the tools it may name; the runner runs them; a second call writes the
  narration. An invented tool name is dropped, never run.
- **keywords** (no model configured, the model failed, or the injection screen fired): the
  platform's own keyword table picks the tools and nothing narrates. It cannot be talked
  into anything, and it is what answers when a model is down.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.compose import compose_reply, facts_of
from app.core.maf_agent import ModelTrace, build_agent
from app.core.models import ModelChain
from app.core.prompts import PLAN_JSON, PLANNER, narrator_instructions, tool_catalogue
from app.core.tools import ToolRunner
from application.ai.safety.untrusted import UntrustedText
from application.capabilities.catalog_intents import CHAT_INTENT_TOOL
from application.chat_keywords import keyword_intents
from application.composer import Composed, narrator_brief
from domain.ai import ChatMessage

log = logging.getLogger("tcc.orchestrator.planner")


@dataclass
class Planned:
    """What planning produced. `composed` is set when the Agent's middleware already composed the reply."""

    mode: str
    narration: str | None = None
    composed: Composed | None = None
    model_used: bool = False
    degraded: bool = False
    trace: ModelTrace = field(default_factory=ModelTrace)


class Planner:
    """Runs one turn's tools, by whichever mode this process and this message allow."""

    def __init__(self, chain: ModelChain, *, allowed_hosts: tuple[str, ...] = ()) -> None:
        self._chain, self._hosts = chain, allowed_hosts

    async def plan(self, runner: ToolRunner) -> Planned:
        """Run the turn's tools and, when a model is in play, collect its narration."""
        if not self._chain.configured or self._chain.screen(runner.question):
            return await self._keywords(runner, Planned("keywords"))
        planned = Planned("tools" if self._chain.tools_available else "json", model_used=True)
        try:
            return await (self._with_tools(runner, planned) if planned.mode == "tools" else self._with_json(runner, planned))
        except Exception as exc:  # noqa: BLE001 - whatever the model layer does, the reader still gets the engine's answer
            log.warning("the model layer failed (%s); answering from the tools alone", type(exc).__name__)
            planned.degraded, planned.narration, planned.composed = True, None, None
            return await self._keywords(runner, planned) if not runner.runs else planned

    # ------------------------------------------------------------------- tools

    async def _with_tools(self, runner: ToolRunner, planned: Planned) -> Planned:
        narration, _ = narrator_instructions()
        captured: dict[str, Any] = {}

        def compose(raw: str) -> str:
            composed = compose_reply(runner.question, runner.runs, raw, self._hosts)
            captured.update(narration=raw, composed=composed)
            return composed.text

        agent = build_agent(self._chain, runner, planned.trace, PLANNER + "\n" + narration, compose)
        await agent.run(UntrustedText(runner.question, "reader question").fenced())
        planned.narration, planned.composed = captured.get("narration"), captured.get("composed")
        return planned

    # -------------------------------------------------------------------- json

    async def _with_json(self, runner: ToolRunner, planned: Planned) -> Planned:
        system = f"{PLAN_JSON}\nTOOLS:\n{tool_catalogue()}"
        asked = [ChatMessage("system", system), ChatMessage("user", UntrustedText(runner.question, "reader question").fenced())]
        turn = await self._chain.complete(asked)
        planned.trace.turns.append(turn)
        planned.trace.prompt_parts.append("\n".join(m.content for m in asked))
        for step in plan_steps(turn.text, runner.max_calls):
            await runner.run(step["tool"], step["args"])
        if runner.runs and not runner.clarify:
            planned.narration = await self._narrate(runner, planned)
        return planned

    async def _narrate(self, runner: ToolRunner, planned: Planned) -> str:
        text, _ = narrator_instructions()
        brief = narrator_brief(
            UntrustedText(runner.question, "reader question").fenced(), runner.tool_names, facts_of(runner.runs),
            notes=[w for run in runner.runs for w in run.envelope.get("warnings") or []],
        )
        asked = [ChatMessage("system", text), ChatMessage("user", "JSON:\n" + json.dumps(brief))]
        turn = await self._chain.complete(asked, prefer=planned.trace.last.provider if planned.trace.last else None)
        planned.trace.turns.append(turn)
        planned.trace.prompt_parts.append("\n".join(m.content for m in asked))
        return turn.text

    # ---------------------------------------------------------------- keywords

    async def _keywords(self, runner: ToolRunner, planned: Planned) -> Planned:
        tools: list[str] = []
        for intent in keyword_intents(runner.question):
            tool = CHAT_INTENT_TOOL.get(intent)
            if tool and tool not in tools:
                tools.append(tool)
        for tool in tools[: runner.max_calls]:
            await runner.run(tool, {})
        if planned.mode != "keywords":
            planned.mode = "keywords"
        return planned


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
