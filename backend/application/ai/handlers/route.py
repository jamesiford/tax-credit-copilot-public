"""RouteQuestionQuery -> the router role's stream, on the OrchestratorAgent."""
from __future__ import annotations

from collections.abc import AsyncIterator

from application.ai.requests import RouteQuestionQuery
from domain.ai import ModelEvent, ModelRole

#: The agent whose prompt teaches routing. Its role, not its name, picks the model.
ROUTER_AGENT = "OrchestratorAgent"


async def handle_route_question(query: RouteQuestionQuery) -> AsyncIterator[ModelEvent]:
    from application.wiring import get_narration_service

    async for event in get_narration_service().stream(ROUTER_AGENT, query.prompt, role=ModelRole.ROUTER):
        yield event
