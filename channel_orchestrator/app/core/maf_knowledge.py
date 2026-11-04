"""Reference text as a framework context provider. [RM-15, ADR-010]

The framework's way to give an agent background is a `ContextProvider`: before the model runs it may add
instructions. This one asks the knowledge port for the passages that bear on the reader's question and adds
them to the instructions as fenced reference text (`knowledge.model_context`), labelled as not being facts.

It adds NO tool, NO message and NO fact: nothing it does reaches the fact index, the ledger or a tool result,
so a figure in a passage cannot become a figure in a reply. If a model repeats one, the narration is dropped
by the same numeric guard that drops any typed digit. The passages it found are kept on the provider so the
turn can print them with their citations beside the narration they may have informed.

A knowledge source that is down or slow costs the reader nothing: the turn goes on without reference text.
Nothing builds this unless the knowledge tier is switched on (`KNOWLEDGE_ENABLED`, off by default).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext, SupportsAgentRun

from application.knowledge import KnowledgePort, Passage, model_context

log = logging.getLogger("tcc.orchestrator.knowledge")
SOURCE_ID = "knowledge"


class KnowledgeContextProvider(ContextProvider):
    """Adds the reader's question's reference passages to the agent's instructions, once per run."""

    def __init__(self, port: KnowledgePort, question: str, *, top: int) -> None:
        super().__init__(SOURCE_ID)
        self._port, self._question, self._top = port, question, top
        self.passages: tuple[Passage, ...] = ()

    async def before_run(
        self, *, agent: SupportsAgentRun, session: AgentSession, context: SessionContext, state: dict[str, Any],
    ) -> None:
        try:
            found = await asyncio.to_thread(self._port.search, self._question, top=self._top)
        except Exception as exc:  # noqa: BLE001 - reference text is optional; the answer does not depend on it
            log.warning("the knowledge source failed (%s); answering without reference text", type(exc).__name__)
            return
        self.passages = tuple(found[: self._top])
        text = model_context(self.passages)
        if text:
            context.extend_instructions(self.source_id, text)
