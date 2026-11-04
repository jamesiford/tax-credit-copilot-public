"""Deciding which tools run, and getting a narration around the results. [CH-08, RM-10a]

The MAF tool-calling `Agent` is THE planner for an open-ended question: the model chooses which of the catalog's
tools to call, in its own loop, against this turn's rules (`maf_tool_rules`), and its output is replaced by the
composed reply. In every mode the model (if there is one) chooses WHICH deterministic tool runs and may write the
connective sentence; the tools' facts are the only source of a figure, and `ToolRunner` enforces whose data it is.

Where no tool-calling model can answer, one of two degraded planners (`degraded.DegradedPlanner`) does, and says
so in `Planned.mode`:

- **tools**: a provider offers tool calling. The Agent.
- **json**: the provider cannot call tools (`AI_GATEWAY_SUPPORTS_TOOLS=false`). `degraded.JsonPlanner`.
- **keywords**: no model is configured, the injection screen fired, or the model layer failed. `degraded.KeywordPlanner`.

A model failure after tools have run keeps what they returned; one before any tool ran falls to the keywords.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

from app.core.degraded import JSON, KEYWORDS, DegradedPlanner, JsonPlanner, KeywordPlanner
from app.core.maf_agent import build_agent
from app.core.maf_knowledge import KnowledgeContextProvider
from app.core.model_access import ModelAccess
from app.core.planned import Planned
from app.core.prompts import PLANNER, narrator_instructions
from app.core.tools import ToolRunner
from application.ai.safety.untrusted import UntrustedText
from application.knowledge import KnowledgePort

log = logging.getLogger("tcc.orchestrator.planner")
TOOLS = "tools"


class Planner:
    """Runs one turn's tools: the Agent when a tool-calling model is reachable, a degraded planner otherwise."""

    def __init__(
        self, chain: ModelAccess, *, allowed_hosts: tuple[str, ...] = (), degraded: Mapping[str, DegradedPlanner] | None = None,
        knowledge: KnowledgePort | None = None, knowledge_top: int = 3,
    ) -> None:
        self._chain, self._hosts = chain, allowed_hosts
        self._knowledge, self._knowledge_top = knowledge, knowledge_top
        self._degraded: Mapping[str, DegradedPlanner] = degraded or {JSON: JsonPlanner(chain), KEYWORDS: KeywordPlanner()}

    async def plan(self, runner: ToolRunner) -> Planned:
        """Run the turn's tools and, when a model is in play, collect its narration."""
        if not self._chain.configured or self._chain.screen(runner.question):
            return await self._degraded[KEYWORDS].plan(runner, Planned(KEYWORDS, hosts=self._hosts))
        agent = self._chain.tools_available
        planned = Planned(TOOLS if agent else JSON, model_used=True, hosts=self._hosts)
        try:
            return await (self._with_agent(runner, planned) if agent else self._degraded[JSON].plan(runner, planned))
        except Exception as exc:  # noqa: BLE001 - whatever the model layer does, the reader still gets the engine's answer
            log.warning("the model layer failed (%s); answering from the tools alone", type(exc).__name__)
            planned.fall_back()
            return await self._degraded[KEYWORDS].plan(runner, planned) if not runner.runs else planned

    async def _with_agent(self, runner: ToolRunner, planned: Planned) -> Planned:
        """The Agent's loop; its only exit is the composed reply, which is also what `planned` keeps."""
        narration, _ = narrator_instructions()

        def compose(raw: str) -> str:
            planned.narrate(raw)
            return planned.composed_for(runner).text

        providers = [KnowledgeContextProvider(self._knowledge, runner.question, top=self._knowledge_top)] if self._knowledge else []
        agent = build_agent(self._chain, runner, planned.trace, PLANNER + "\n" + narration, compose, providers)
        await agent.run(UntrustedText(runner.question, "reader question").fenced())
        planned.reference = providers[0].passages if providers else ()
        return planned
