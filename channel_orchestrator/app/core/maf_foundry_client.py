"""The framework's own chat client for the `foundry` provider: the account's OpenAI host, Entra identity, no key. [RM-09]

`agent_framework_openai.OpenAIChatCompletionClient` is the MAF primitive for "a model behind an OpenAI-style
endpoint". `FoundryChatClient` is the other candidate and is not used: it takes only a project endpoint and
reaches the model through the project's `services.ai.azure.com` host, which the hosted runtime could not
resolve (D-101, finding F-02). Here the client is given the account's `openai.azure.com` host as its
`base_url` and a token provider as its credential, so the same account, token and deployment work from the
hosted runtime and the wire (chat completions v1) is the one the shared adapter has always used.

What `ModelChain` did around each call is kept as chat middleware, in this order: the egress rule (an
identifier never leaves), the per-call deadline, and the trace the audit report reads. The tool loop,
telemetry and function middleware are the framework's. `ComposeMiddleware` still replaces the narrator's words
with the composer's verbatim output; nothing here changes what a reader is shown.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from agent_framework import ChatContext, ChatMiddleware
from agent_framework_openai import OpenAIChatCompletionClient

from app.core.maf_chat import ModelTrace, as_chat_messages, loop_limits
from app.core.model_access import FoundryModelAccess, TokenProvider
from app.core.models import ModelTurn
from application.ai.egress import build_egress_policy
from domain.ai import EgressRefused, ModelRole, ModelTimeout, ToolCall, supports_temperature

PROVIDER = "foundry"
Next = Callable[[], Awaitable[None]]


def prompt_of(context: ChatContext) -> str:
    """Everything the model is sent, as the egress rule and the audit hash have always read it."""
    cached = context.metadata.get("prompt")
    if cached is None:
        cached = context.metadata["prompt"] = "\n".join(
            m.content for m in as_chat_messages(context.messages, (context.options or {}).get("instructions"))
        )
    return cached


class EgressGuard(ChatMiddleware):
    """Refuses a call whose prompt carries what the egress policy keeps in (an employee identifier, always)."""

    def __init__(self, policy: str) -> None:
        self._policy = build_egress_policy(policy)

    async def process(self, context: ChatContext, call_next: Next) -> None:
        decision = self._policy.prepare(prompt_of(context), role=ModelRole.NARRATOR, provider=PROVIDER)
        if not decision.allowed:
            raise EgressRefused(decision.reason or "the egress policy refused this prompt")
        await call_next()


class Deadline(ChatMiddleware):
    """Bounds one model call, because the SDK's own timeout is minutes and a turn has seconds."""

    def __init__(self, seconds: float) -> None:
        self._seconds = seconds

    async def process(self, context: ChatContext, call_next: Next) -> None:
        try:
            await asyncio.wait_for(call_next(), self._seconds)
        except asyncio.TimeoutError as exc:
            raise ModelTimeout("the model did not answer in time") from exc


class TraceModel(ChatMiddleware):
    """Records the prompt sent and, once the model answers, the turn it took: what the narration audit reports."""

    def __init__(self, trace: ModelTrace, model: str) -> None:
        self._trace, self._model = trace, model

    async def process(self, context: ChatContext, call_next: Next) -> None:
        self._trace.prompt_parts.append(prompt_of(context))
        await call_next()
        result = context.result
        calls = tuple(
            ToolCall(c.call_id, c.name, c.arguments if isinstance(c.arguments, str) else "{}")
            for message in getattr(result, "messages", None) or [] for c in message.contents if c.type == "function_call"
        )
        self._trace.turns.append(ModelTurn(
            getattr(result, "text", "") or "", calls, PROVIDER, getattr(result, "model", None) or self._model, (PROVIDER,),
        ))


@lru_cache(maxsize=4)
def entra_token_provider(scope: str) -> TokenProvider:
    """A bearer-token provider over `DefaultAzureCredential`: `az login` locally, the managed identity deployed.

    Built once per process so the credential's token cache is shared by every turn. The blocking fetch runs in a
    thread so a slow metadata endpoint cannot stall the event loop that is serving other turns.
    """
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    provider = get_bearer_token_provider(DefaultAzureCredential(), scope)

    async def token() -> str:
        return await asyncio.to_thread(provider)

    return token


def foundry_client(access: FoundryModelAccess, trace: ModelTrace, *, max_calls: int) -> OpenAIChatCompletionClient:
    """MAF's OpenAI client for the account's v1 host, authenticated by token provider only."""
    return OpenAIChatCompletionClient(
        model=access.model, base_url=access.base_url, credential=access.credential or entra_token_provider(access.scope),
        middleware=[EgressGuard(access.egress_policy), Deadline(access.timeout_seconds), TraceModel(trace, access.model)],
        function_invocation_configuration=loop_limits(max_calls),
    )


def foundry_options(access: FoundryModelAccess) -> dict[str, Any]:
    """Run options for the model: the temperature the shared adapter sent, for the deployments that accept one."""
    return {"temperature": 0.2} if supports_temperature(access.model) else {}
