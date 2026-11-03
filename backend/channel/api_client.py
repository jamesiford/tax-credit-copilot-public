"""The gateway's one outbound call: the API, as itself. [CH-06]

The gateway authenticates to the API with its own managed identity (an app-only token
for `API_AUDIENCE`, holding the role `TCC.Agent`) and names the person it acts for in
`X-TCC-Acting-User`, the header the API's guard parses for exactly this. It forwards
the correlation id so the API's records join up with the gateway's.

Nothing here knows what a tool is. A failure to reach the API is one of three typed
`ApiUnavailable` codes, so the pipeline can say "the API did not answer" and
"the API answered no" differently.

The response is read with a hard cap (`MAX_RESPONSE_BYTES`): a tool envelope is a few
kilobytes, so one that is not is a fault, and the gateway will not buffer it.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from application.acting_user import HEADER as ACTING_USER_HEADER
from application.acting_user import encode
from application.identity import ActingUser
from channel.config import MAX_DOWNLOAD_BYTES, MAX_RESPONSE_BYTES, GatewaySettings


class ApiUnavailable(Exception):
    """The API did not give a usable answer. `code` is `api_unreachable`, `timeout` or `bad_response`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class ApiResult:
    """What the API answered: its status, headers and body (a JSON object, or raw bytes for a file)."""

    status: int
    body: dict[str, Any]
    raw: bytes = b""
    headers: dict[str, str] | None = None


def acting_header(acting: ActingUser) -> str:
    """`X-TCC-Acting-User` for `acting`: the same fields the API's parser reads, no more."""
    payload = {
        "oid": acting.oid, "tid": acting.tenant_id, "name": acting.display_name, "upn": acting.upn,
        "channel": acting.channel, "conversation_id": acting.conversation_id,
        "correlation_id": acting.correlation_id, "assurance": acting.assurance,
    }
    return encode({k: v for k, v in payload.items() if v is not None})


def managed_identity_token(settings: GatewaySettings) -> Callable[[], str]:
    """A bearer-token provider over `DefaultAzureCredential` (managed identity when deployed)."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    return lambda: credential.get_token(settings.api_scope).token


class ApiClient:
    """Calls `POST /api/capabilities/{tool}` and fetches artifacts, as the gateway."""

    def __init__(
        self, settings: GatewaySettings, token_provider: Callable[[], str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings, self._token = settings, token_provider
        self._http = httpx.AsyncClient(
            base_url=settings.api_base_url, transport=transport,
            timeout=httpx.Timeout(settings.request_timeout_seconds, connect=min(10.0, settings.request_timeout_seconds)),
        )

    async def _headers(self, acting: ActingUser) -> dict[str, str]:
        token = await asyncio.to_thread(self._token)
        headers = {"Authorization": f"Bearer {token}", ACTING_USER_HEADER: acting_header(acting)}
        if acting.correlation_id:
            headers["X-Correlation-Id"] = acting.correlation_id
        return headers

    async def _send(
        self, method: str, path: str, acting: ActingUser, *, limit: int = MAX_RESPONSE_BYTES, **kwargs: Any,
    ) -> tuple[int, dict[str, str], bytes]:
        try:
            headers = await self._headers(acting)
            async with self._http.stream(method, path, headers=headers, **kwargs) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ApiUnavailable("bad_response", "the API's response exceeded the size the gateway will accept")
                return response.status_code, dict(response.headers), bytes(data)
        except httpx.TimeoutException as exc:
            raise ApiUnavailable("timeout", "the API did not answer in time") from exc
        except httpx.HTTPError as exc:
            raise ApiUnavailable("api_unreachable", f"the API could not be reached ({type(exc).__name__})") from exc

    async def call_tool(
        self, tool: str, args: dict[str, Any], acting: ActingUser, *,
        idempotency_key: str | None = None, confirmation_token: str | None = None,
    ) -> ApiResult:
        """Run one tool on the API for `acting`."""
        body = {"args": args, "idempotency_key": idempotency_key, "confirmation_token": confirmation_token}
        status, headers, raw = await self._send(
            "POST", f"/api/capabilities/{tool}", acting, json={k: v for k, v in body.items() if v is not None},
        )
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as exc:
            raise ApiUnavailable("bad_response", "the API did not return JSON") from exc
        return ApiResult(status, parsed if isinstance(parsed, dict) else {"detail": parsed}, headers=headers)

    async def fetch(self, path: str, acting: ActingUser) -> ApiResult:
        """GET `path` (an API-relative artifact path) and return the bytes untouched."""
        status, headers, raw = await self._send("GET", path, acting, limit=MAX_DOWNLOAD_BYTES)
        return ApiResult(status, {}, raw, headers)

    async def reachable(self, acting: ActingUser) -> bool:
        """True if the API's liveness probe answers; never raises."""
        try:
            status, _, _ = await self._send("GET", "/api/health", acting)
        except ApiUnavailable:
            return False
        return status == 200

    async def close(self) -> None:
        await self._http.aclose()
