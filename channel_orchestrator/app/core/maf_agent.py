"""The Microsoft Agent Framework layer: an Agent whose only exit is the composer. [CH-08]

`build_agent` returns an MAF `Agent` with the model's tool-calling loop and one middleware
that is the structural half of "agents narrate, tools calculate": whatever text the model
produces, the Agent's RESULT is replaced by `composer.compose(...)` output built from the
tools' own blocks and facts. There is no code path from the model's words to the reader that
does not go through the numeric guard, because the only thing the Agent can return is the
middleware's replacement.

Which chat client drives the model is decided by `model_access.select_model_access` from
`AI_PROVIDER_CHAIN` (RM-09): a foundry-only chain gets the framework's own OpenAI client
(`maf_foundry_client`); a chain that names the customer's gateway gets `PortChatClient`, a bridge
from MAF to the shared model adapters (`ModelChain`) that keeps the provider failover and the
gateway's egress rule. Either way MAF's tool loop is bounded by the turn's tool budget and runs
tools one at a time (their order is the order of the answer).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import (
    Agent, AgentContext, AgentMiddleware, AgentResponse, BaseChatClient, ChatMiddlewareLayer, ChatResponse, Content,
    FunctionInvocationLayer, FunctionTool, Message,
)

from app.core.maf_catalog_tools import TURN, catalog_tools
from app.core.maf_chat import ModelTrace, as_chat_messages, loop_limits
from app.core.maf_foundry_client import foundry_client, foundry_options
from app.core.maf_tool_call import CallAndCapture
from app.core.maf_tool_rules import RecordUnregisteredCalls, tool_rules
from app.core.model_access import FoundryModelAccess, ModelAccess
from app.core.models import ModelChain, ModelTurn
from app.core.tools import ToolRunner
from domain.ai import ToolSpec

log = logging.getLogger("tcc.orchestrator.maf")
#: What the framework answers when the tool loop stops at its budget; live it surfaced as the reply's first line.
LIMIT_NOTICE = "Function invocation limit reached"


def _as_response(turn: ModelTurn) -> ChatResponse:
    """A model adapter's whole turn as the framework's response: the text first, then each tool call the model asked for."""
    contents: list[Any] = [Content.from_function_call(call_id=c.id, name=c.name, arguments=c.arguments or "{}") for c in turn.tool_calls]
    if turn.text:
        contents.insert(0, turn.text)
    return ChatResponse(messages=[Message("assistant", contents or [""])])


class PortChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, BaseChatClient):
    """MAF's chat-client contract over `ModelChain`: messages and tools in, one whole answer out."""

    def __init__(self, chain: ModelChain, trace: ModelTrace, *, max_calls: int) -> None:
        super().__init__(function_invocation_configuration=loop_limits(max_calls))
        self._chain, self._trace = chain, trace

    def _inner_get_response(self, *, messages: Any, stream: bool, options: Any, **kwargs: Any) -> Awaitable[ChatResponse]:
        if stream:
            raise NotImplementedError("published agents do not stream; the reply is composed whole")
        return self._respond(messages, options)

    async def _respond(self, messages: Any, options: Any) -> ChatResponse:
        tools = [ToolSpec(t.name, t.description, t.parameters()) for t in (options.get("tools") or [])]
        chat = as_chat_messages(messages, options.get("instructions"))
        self._trace.sent(chat)
        turn = await self._chain.complete(chat, tools, prefer=self._trace.last.provider if self._trace.last else None)
        self._trace.took(turn)
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


def function_tools(_turn: object | None = None) -> list[FunctionTool]:
    """The tools a model may name, generated from the catalog. They carry no turn: `_turn` is accepted so callers may
    pass it, and the turn itself reaches the tools and the rules through `function_invocation_kwargs`."""
    return catalog_tools()


def chat_client_for(model: ModelAccess, trace: ModelTrace, *, max_calls: int) -> tuple[BaseChatClient, dict[str, Any]]:
    """The chat client for `model` and the run options it needs: the framework's own for a foundry-only chain,
    `PortChatClient` over `ModelChain` for every other (the selection rule is `model_access.select_model_access`)."""
    if isinstance(model, FoundryModelAccess):
        return foundry_client(model, trace, max_calls=max_calls), foundry_options(model)
    if isinstance(model, ModelChain):
        return PortChatClient(model, trace, max_calls=max_calls), {}
    raise TypeError(f"no chat client for {type(model).__name__}")


def build_agent(chain: ModelAccess, runner: ToolRunner, trace: ModelTrace, instructions: str, compose: Callable[[str], str]) -> Agent:
    """The turn's Agent: the generated tools, the turn's rules as middleware, and an output bound to the composer.

    Function middleware runs in the order `maf_tool_rules` lists it, then `CallAndCapture`; the chat middleware
    records a tool name the model asked for that is not registered (a commit, an invented one). The turn is the
    agent's default `additional_function_arguments`, which is what `function_invocation_kwargs` is per run.
    """
    client, options = chat_client_for(chain, trace, max_calls=runner.max_calls)
    return Agent(
        client, instructions, tools=function_tools(),
        middleware=[ComposeMiddleware(compose), *tool_rules(), CallAndCapture(), RecordUnregisteredCalls(runner)],
        default_options={**options, "additional_function_arguments": {TURN: runner}},
    )
