"""`ChatModel` over ANY OpenAI-compatible chat-completions endpoint. [AI-03]

The customer's gateway is an HTTPS service we know little about beyond "OpenAI
style, streaming, tool calling" — so this adapter is deliberately dialect-tolerant
and everything it cannot know is configuration (`GatewaySettings`). It streams
server-sent events (or reads one JSON body when streaming is off), reports usage
when the gateway does, hands tool calls back for the CALLER to run, and maps every
failure onto the small taxonomy in `domain.ai`.

The `httpx` client is injectable so tests drive the same code against the mock
gateway through an ASGI transport; abandoning the stream closes the connection, so
a disconnected browser stops the upstream call.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

import httpx

from application.ai.gateway_settings import GatewaySettings
from domain.ai import (
    ChatMessage, ModelEvent, ModelTimeout, ModelUnavailable, ProviderStatus, StreamEnd, ToolSpec,
)
from infrastructure.ai.auth import NoAuth, RequestAuthenticator
from infrastructure.ai.openai_wire import (
    ToolCallAssembler, build_body, build_headers, build_url, decode_chunk, decode_message, iter_sse, map_status,
)

_TIMEOUTS = (httpx.TimeoutException,)


class OpenAICompatibleChatModel:
    name = "gateway"

    def __init__(
        self, settings: GatewaySettings, authenticator: RequestAuthenticator | None = None, *,
        client: httpx.AsyncClient | None = None, request_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._settings = settings
        self._auth = authenticator or NoAuth()
        self._client = client
        self._request_id = request_id

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            s = self._settings
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(s.timeout_s, connect=s.connect_timeout_s), verify=s.tls_verify,
            )
        return self._client

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, "ready", self._settings.endpoint.split("//", 1)[-1].split("/", 1)[0])

    async def stream(
        self, messages: Sequence[ChatMessage], *, model: str, temperature: float | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[ModelEvent]:
        s, request_id = self._settings, self._request_id()
        streaming = s.streaming
        headers = build_headers(s, await self._auth.headers(), request_id, streaming)
        body = build_body(s, model, messages, temperature=temperature, tools=tools, stream=streaming)
        try:
            if streaming:
                async for event in self._stream(build_url(s, model), headers, body, request_id, model):
                    yield event
            else:
                async for event in self._whole(build_url(s, model), headers, body, request_id, model):
                    yield event
        except _TIMEOUTS as exc:
            raise ModelTimeout(f"the gateway did not answer in time (request {request_id})") from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"the gateway connection failed: {type(exc).__name__} (request {request_id})") from exc

    def _fail(self, response: httpx.Response, request_id: str) -> Exception:
        if response.status_code == 401:
            self._auth.invalidate()
        return map_status(response.status_code, response.headers, request_id)

    async def _stream(self, url: str, headers: dict[str, str], body: dict[str, Any], request_id: str, model: str):
        tools, finish, state = ToolCallAssembler(), None, {"done": False}
        async with self._http().stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                raise self._fail(response, request_id)
            async for payload in iter_sse(response.aiter_lines(), state):
                events, reason = decode_chunk(payload, tools)
                finish = reason or finish
                for event in events:
                    yield event
        if not state["done"] and finish is None:
            raise ModelUnavailable(f"the gateway's stream ended before it was complete (request {request_id})")
        for call in tools.drain():
            yield call
        yield StreamEnd(provider=self.name, model=model, finish_reason=finish)

    async def _whole(self, url: str, headers: dict[str, str], body: dict[str, Any], request_id: str, model: str):
        response = await self._http().post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise self._fail(response, request_id)
        events, finish = decode_message(response.json())
        for event in events:
            yield event
        yield StreamEnd(provider=self.name, model=model, finish_reason=finish)
