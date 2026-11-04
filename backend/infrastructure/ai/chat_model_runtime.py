"""An `AgentRuntime` over a `ChatModel`: the gateway as a provider. [AI-03]

An agent is its instructions plus a model. For a plain OpenAI-compatible endpoint
the instructions are the system message, the brief is the user message, and the
model is the one configured for the agent's ROLE on this provider. No tool is
offered: agents narrate, tools calculate [ADR-004], so a `ToolCall` here would be
a model misbehaving and is dropped, not run.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from application.ai.ports import ChatModel
from application.ai.settings import AiSettings
from domain.ai import (
    AgentSpec, ChatMessage, ModelEvent, ProviderStatus, StreamEnd, ToolCall, supports_temperature,
)


class ChatModelAgentRuntime:
    """Adapts a `ChatModel` (a bare model endpoint) to the `AgentRuntime` the chain runs: instructions become the system message."""

    def __init__(self, chat_model: ChatModel, settings: AiSettings, *, name: str | None = None) -> None:
        self._chat, self._settings = chat_model, settings
        self.name = name or chat_model.name

    def ready_for(self, agent_name: str) -> bool:
        return True  # specs are in-process: nothing to publish

    def version_of(self, agent_name: str) -> str | None:
        return None

    def status(self) -> ProviderStatus:
        return self._chat.status()

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        model = self._settings.model_for(spec.role, self.name)
        temperature = spec.temperature if spec.temperature is not None and supports_temperature(model) else None
        messages = [ChatMessage("system", spec.instructions), ChatMessage("user", prompt)]
        async for event in self._chat.stream(messages, model=model, temperature=temperature):
            if isinstance(event, ToolCall):
                continue
            yield event
            if isinstance(event, StreamEnd):
                return
