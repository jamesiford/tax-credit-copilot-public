"""NarrateBriefQuery -> the named agent's stream."""
from __future__ import annotations

from collections.abc import AsyncIterator

from application.ai.requests import NarrateBriefQuery
from domain.ai import ModelEvent


async def handle_narrate_brief(query: NarrateBriefQuery) -> AsyncIterator[ModelEvent]:
    from application.wiring import get_narration_service

    async for event in get_narration_service().stream(query.agent_name, query.prompt):
        yield event
