"""The Microsoft Agent Framework layer: an Agent whose only exit is the composer. [CH-08]

`build_agent` returns an MAF `Agent` with the model's tool-calling loop and one middleware
that is the structural half of "agents narrate, tools calculate": whatever text the model
produces, the Agent's RESULT is replaced by `composer.compose(...)` output built from the
tools' own blocks and facts. There is no code path from the model's words to the reader that
does not go through the numeric guard, because the only thing the Agent can return is the
middleware's replacement.

The chat client is a bridge from MAF to the shared model adapters (`ModelChain`), so MAF's
function-invocation loop drives a model that may be a Foundry deployment or the customer's
gateway, under the same egress rule as everywhere else. MAF's tool loop is bounded by the
turn's tool budget and runs tools one at a time (their order is the order of the answer).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    Agent, AgentContext, AgentMiddleware, AgentResponse, BaseChatClient, ChatResponse, Content, FunctionInvocationLayer,
    FunctionTool, Message,
)

from app.core.models import ModelChain, ModelTurn
from app.core.tools import ToolRunner, model_tools, offered_schema
from domain.ai import ChatMessage, ToolCall, ToolSpec

log = logging.getLogger("tcc.orchestrator.maf")
#: What the framework answers when the tool loop stops at its budget; live it surfaced as the reply's first line.
LIMIT_NOTICE = "Function invocation limit reached"


@dataclass
class ModelTrace:
    """What the model layer did this turn, for the audit report. Holds no text."""

    turns: list[ModelTurn] = field(default_factory=list)
    prompt_parts: list[str] = field(default_factory=list)

    @property
    def last(self) -> ModelTurn | None:
        return self.turns[-1] if self.turns else None


def _as_chat_messages(messages: Any, instructions: str | None) -> list[ChatMessage]:
    """MAF's messages as the model adapters' `ChatMessage`s."""
    out = [ChatMessage("system", instructions)] if instructions else []
    for message in messages:
        calls = tuple(
            ToolCall(c.call_id, c.name, c.arguments if isinstance(c.arguments, str) else json.dumps(c.arguments or {}))
            for c in message.contents if c.type == "function_call"
        )
        results = [c for c in message.contents if c.type == "function_result"]
        if results:
            out += [ChatMessage("tool", str(r.result), tool_call_id=r.call_id) for r in results]
        elif calls:
            out.append(ChatMessage("assistant", message.text or "", tool_calls=calls))
        else:
            out.append(ChatMessage(str(message.role), message.text or ""))
    return out


def _as_response(turn: ModelTurn) -> ChatResponse:
    contents: list[Any] = [Content.from_function_call(call_id=c.id, name=c.name, arguments=c.arguments or "{}") for c in turn.tool_calls]
    if turn.text:
        contents.insert(0, turn.text)
    return ChatResponse(messages=[Message("assistant", contents or [""])])


class PortChatClient(FunctionInvocationLayer, BaseChatClient):
    """MAF's chat-client contract over `ModelChain`: messages and tools in, one whole answer out."""

    def __init__(self, chain: ModelChain, trace: ModelTrace, *, max_calls: int, on_unknown: Callable[[str], None]) -> None:
        super().__init__(function_invocation_configuration={
            "max_iterations": max_calls + 2, "max_function_calls": max_calls + 1, "allow_concurrent_invocation": False,
        })
        self._chain, self._trace, self._on_unknown = chain, trace, on_unknown

    def _inner_get_response(self, *, messages: Any, stream: bool, options: Any, **kwargs: Any) -> Awaitable[ChatResponse]:
        if stream:
            raise NotImplementedError("published agents do not stream; the reply is composed whole")
        return self._respond(messages, options)

    async def _respond(self, messages: Any, options: Any) -> ChatResponse:
        tools = [ToolSpec(t.name, t.description, t.parameters()) for t in (options.get("tools") or [])]
        chat = _as_chat_messages(messages, options.get("instructions"))
        self._trace.prompt_parts.append("\n".join(m.content for m in chat))
        turn = await self._chain.complete(chat, tools, prefer=self._trace.last.provider if self._trace.last else None)
        self._trace.turns.append(turn)
        known = {t.name for t in tools}
        for call in turn.tool_calls:
            if call.name not in known:  # MAF answers an unknown call with an error; this records the attempt
                self._on_unknown(call.name)
        return _as_response(turn)


class ComposeMiddleware(AgentMiddleware):
    """Replaces whatever the model said with the composed, guarded reply."""

    def __init__(self, compose: Callable[[str], str]) -> None:
        self._compose = compose

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        await call_next()
        raw = context.result.text if context.result is not None else ""
        if raw.startswith(LIMIT_NOTICE):
            raw = ""  # the framework's own stop message is not the model's narration
        context.result = AgentResponse(messages=[Message("assistant", [self._compose(raw)])])


def function_tools(runner: ToolRunner) -> list[FunctionTool]:
    """One MAF tool per tool a model may name. A commit is not among them."""
    def make(name: str) -> FunctionTool:
        async def call(**proposed: Any) -> str:
            return json.dumps(await runner.run(name, proposed), default=str)

        spec = model_tools()[name]
        return FunctionTool(name=name, description=spec.description, func=call, input_model=offered_schema(spec))

    return [make(name) for name in sorted(model_tools())]


def build_agent(chain: ModelChain, runner: ToolRunner, trace: ModelTrace, instructions: str, compose: Callable[[str], str]) -> Agent:
    """The turn's Agent: tools bound to this turn's runner, output bound to the composer."""
    client = PortChatClient(chain, trace, max_calls=runner.max_calls, on_unknown=runner.refused.append)
    return Agent(client, instructions, tools=function_tools(runner), middleware=[ComposeMiddleware(compose)])
