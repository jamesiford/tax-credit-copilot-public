"""The OpenAI-compatible wire format, in one place. [AI-03]

URL and header building, request bodies, server-sent-event parsing, chunk decoding
and HTTP error mapping live here and nowhere else (DRY): the adapter orchestrates,
this knows the dialect. Two URL styles exist because gateways differ — `openai_v1`
(`/v1/chat/completions`, model in the body) and `azure_deployments`
(`/openai/deployments/{model}/chat/completions?api-version=…`, model in the path).

Nothing here logs a prompt, a completion or a header.
"""
from __future__ import annotations

import email.utils
import json
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any
from urllib.parse import quote

from application.ai.gateway_settings import GatewaySettings
from domain.ai import (
    ChatMessage, ModelAuth, ModelBadRequest, ModelError, ModelRateLimited, ModelUnavailable, ModelUsage,
    TextDelta, ToolCall, ToolSpec,
)

USER_AGENT = "tax-credit-copilot/1 (+model-gateway)"


def build_url(settings: GatewaySettings, model: str) -> str:
    """The chat-completions URL for `model` in the configured dialect."""
    if settings.api_style == "azure_deployments":
        return (f"{settings.endpoint}/openai/deployments/{quote(model, safe='')}/chat/completions"
                f"?api-version={quote(settings.api_version, safe='')}")
    return f"{settings.endpoint}/v1/chat/completions"


def build_headers(settings: GatewaySettings, auth_headers: Mapping[str, str], request_id: str, streaming: bool) -> dict[str, str]:
    """Static headers, then non-secret extras, then auth — auth wins a collision."""
    headers = {
        "Content-Type": "application/json", "User-Agent": USER_AGENT, "X-Request-Id": request_id,
        "Accept": "text/event-stream" if streaming else "application/json",
    }
    headers.update(settings.extra_headers)
    headers.update(auth_headers)
    return headers


def _message(m: ChatMessage) -> dict[str, Any]:
    body: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_call_id:
        body["tool_call_id"] = m.tool_call_id
    if m.tool_calls:
        body["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in m.tool_calls
        ]
    return body


def build_body(
    settings: GatewaySettings, model: str, messages: Sequence[ChatMessage], *, temperature: float | None,
    tools: Sequence[ToolSpec], stream: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {"messages": [_message(m) for m in messages], "stream": stream}
    if settings.api_style != "azure_deployments":
        body["model"] = model
    if temperature is not None:
        body["temperature"] = temperature
    if stream:
        body["stream_options"] = {"include_usage": True}
    if tools:
        body["tools"] = [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": dict(t.parameters)}} for t in tools]
    return body


# ------------------------------------------------------------------- the stream


async def iter_sse(lines: AsyncIterator[str], state: dict[str, bool] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Decoded JSON payloads of `data:` lines until `[DONE]`.

    Comments (`:`) and other fields are ignored; a payload that is not JSON is a
    broken stream, not something to skip silently. `state["done"]` is set when the
    terminator arrives, so the caller can tell a finished stream from a cut one.
    """
    async for raw in lines:
        line = raw.strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            if state is not None:
                state["done"] = True
            return
        try:
            payload = json.loads(data)
        except ValueError as exc:
            raise ModelUnavailable("the gateway sent a malformed stream event") from exc
        if isinstance(payload, dict):
            yield payload


class ToolCallAssembler:
    """Tool calls arrive in fragments keyed by index; emit each once, complete."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def add(self, fragments: Sequence[Mapping[str, Any]]) -> None:
        for fragment in fragments:
            slot = self._calls.setdefault(int(fragment.get("index", 0)), {"id": "", "name": "", "arguments": ""})
            slot["id"] = fragment.get("id") or slot["id"]
            function = fragment.get("function") or {}
            slot["name"] += function.get("name") or ""
            slot["arguments"] += function.get("arguments") or ""

    def drain(self) -> list[ToolCall]:
        calls = [ToolCall(c["id"], c["name"], c["arguments"] or "{}") for _, c in sorted(self._calls.items()) if c["name"]]
        self._calls.clear()
        return calls


def usage_of(payload: Mapping[str, Any]) -> ModelUsage | None:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return None
    return ModelUsage(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))


def decode_chunk(payload: Mapping[str, Any], tools: ToolCallAssembler) -> tuple[list[Any], str | None]:
    """Events and finish reason carried by one streamed chunk."""
    events: list[Any] = []
    finish = None
    for choice in payload.get("choices") or []:
        delta = choice.get("delta") or {}
        if delta.get("content"):
            events.append(TextDelta(delta["content"]))
        if delta.get("tool_calls"):
            tools.add(delta["tool_calls"])
        finish = choice.get("finish_reason") or finish
    if (usage := usage_of(payload)) is not None:
        events.append(usage)
    return events, finish


def _whole_tool_calls(message: Mapping[str, Any]) -> list[ToolCall]:
    """The tool calls a non-streaming message carries, already assembled."""
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        calls.append(ToolCall(call.get("id", ""), function.get("name", ""), function.get("arguments") or "{}"))
    return calls


def decode_message(payload: Mapping[str, Any]) -> tuple[list[Any], str | None]:
    """Events and finish reason of a non-streaming completion."""
    events: list[Any] = []
    finish = None
    for choice in payload.get("choices") or []:
        message = choice.get("message") or {}
        if message.get("content"):
            events.append(TextDelta(message["content"]))
        events.extend(_whole_tool_calls(message))
        finish = choice.get("finish_reason") or finish
    if (usage := usage_of(payload)) is not None:
        events.append(usage)
    return events, finish


# ----------------------------------------------------------------------- errors


def retry_after_seconds(value: str | None, now: float | None = None) -> float | None:
    """`Retry-After` as seconds: a number, or an HTTP date."""
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    when = email.utils.parsedate_to_datetime(value) if email.utils.parsedate_tz(value) else None
    return None if when is None else max(when.timestamp() - (time.time() if now is None else now), 0.0)


def map_status(status: int, headers: Mapping[str, str], request_id: str) -> ModelError:
    """An HTTP failure as the taxonomy. The body is NOT included: it can echo a prompt."""
    suffix = f" (status {status}, request {request_id})"
    if status in (401, 403):
        return ModelAuth("the gateway refused our credentials" + suffix)
    if status == 429:
        return ModelRateLimited("the gateway is rate limiting us" + suffix,
                                retry_after_seconds(headers.get("retry-after")))
    if status >= 500 or status in (408, 425):
        return ModelUnavailable("the gateway failed" + suffix)
    return ModelBadRequest("the gateway rejected the request" + suffix)
