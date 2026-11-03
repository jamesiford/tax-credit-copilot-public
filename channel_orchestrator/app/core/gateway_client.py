"""The orchestrator's one outbound dependency: the channel gateway. [CH-08]

Every figure comes from `POST /channel/v1/tools/{tool}` and every narration is reported to
`POST /channel/v1/audit/narration`, both as the orchestrator's own managed identity (an
app-only token for the gateway's audience, holding `Channel.Invoke`) with the acting user
in the `X-Acting-*` headers. The token is requested per call from the credential, never
held in a field, never logged, and never forwarded anywhere but the gateway.

A failure to reach the gateway is a `GatewayReply` with a stable error code, not an
exception: a turn that cannot get an answer says so in a sentence, and the caller never
has to tell a transport failure from a refusal by catching the right class.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.identity import ActingIdentity

log = logging.getLogger("tcc.orchestrator.gateway")


@dataclass(frozen=True)
class GatewayReply:
    """A tool envelope (`ok`) or the stable error body, with the HTTP status."""

    status: int
    body: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == 200 and "error" not in self.body

    @property
    def error_code(self) -> str:
        return str((self.body.get("error") or {}).get("code") or ("ok" if self.ok else f"http_{self.status}"))

    @property
    def error_message(self) -> str:
        return str((self.body.get("error") or {}).get("message") or "")


def _unreachable(code: str) -> GatewayReply:
    return GatewayReply(0, {"error": {"code": code, "message": "the channel gateway did not answer", "retryable": True}})


class GatewayClient:
    """Calls the gateway for one acting user at a time."""

    def __init__(
        self, base_url: str, token_provider: Callable[[], str], *, timeout_seconds: float = 40.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token_provider
        self._http = httpx.AsyncClient(
            base_url=base_url, transport=transport, timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
        )

    async def _headers(self, who: ActingIdentity) -> dict[str, str]:
        token = await asyncio.to_thread(self._token)
        return {"Authorization": f"Bearer {token}", **who.gateway_headers()}

    async def _post(self, path: str, who: ActingIdentity, body: dict[str, Any]) -> GatewayReply:
        try:
            response = await self._http.post(path, json=body, headers=await self._headers(who))
        except httpx.TimeoutException:
            return _unreachable("timeout")
        except Exception as exc:  # noqa: BLE001 - a credential or transport fault is "unreachable", not a crash
            log.warning("gateway call failed: %s", type(exc).__name__)
            return _unreachable("gateway_unreachable")
        try:
            parsed = response.json()
        except ValueError:
            return GatewayReply(response.status_code, {"error": {"code": "bad_response", "message": "the gateway did not return JSON"}})
        return GatewayReply(response.status_code, parsed if isinstance(parsed, dict) else {"detail": parsed})

    async def call_tool(
        self, who: ActingIdentity, tool: str, args: dict[str, Any], *,
        idempotency_key: str | None = None, confirmation_token: str | None = None,
    ) -> GatewayReply:
        """Run one tool as `who`."""
        body: dict[str, Any] = {"args": args}
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        if confirmation_token:
            body["confirmation_token"] = confirmation_token
        return await self._post(f"/channel/v1/tools/{tool}", who, body)

    async def report_narration(self, who: ActingIdentity, report: dict[str, Any]) -> GatewayReply:
        """File one narration report; the caller decides what a failure means."""
        return await self._post("/channel/v1/audit/narration", who, report)

    async def close(self) -> None:
        await self._http.aclose()


def managed_identity_token(scope: str) -> Callable[[], str]:
    """A bearer-token provider over `DefaultAzureCredential` (the hosted agent's identity when deployed)."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    return lambda: credential.get_token(scope).token
