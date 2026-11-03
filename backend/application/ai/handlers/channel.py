"""ChannelNarrationQuery -> the ChannelNarratorAgent's stream."""
from __future__ import annotations

from collections.abc import AsyncIterator

from application.ai.requests import ChannelNarrationQuery
from domain.ai import ModelEvent

CHANNEL_NARRATOR = "ChannelNarratorAgent"


async def handle_channel_narration(query: ChannelNarrationQuery) -> AsyncIterator[ModelEvent]:
    from application.wiring import get_narration_service

    async for event in get_narration_service().stream(CHANNEL_NARRATOR, query.prompt):
        yield event
