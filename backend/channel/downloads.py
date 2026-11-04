"""`GET /channel/v1/downloads/{ticket}`: a claim package, by ticket. [CH-06, BLOB-4]

A Teams card opens the link in a browser, which has no bearer token, so the ticket
itself is the credential: 256 bits, single use, fifteen minutes, bound to the person
it was minted for (`claim_package_link`). A valid token is optional; when one is
presented it must belong to the ticket's person, and that is checked BEFORE the
ticket is spent so a wrong person cannot burn somebody else's link.

Two steps, both through the API as the gateway: spend the ticket (`claim_package_redeem`
says whose it was and which artifact), then stream the artifact as THAT person, so the
API's `artifact_access` row and the gateway's audit event both name them. The bytes
are streamed through the artifact service; no storage address or SAS is ever produced.

The ticket is never logged. A refusal before the ticket is spent has no person to
attribute it to, so it is a response and a log line, not an audit row.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from application.channel_audit import AuditCall, ChannelAuditor
from application.identity import ActingUser
from channel.api_client import ApiClient, ApiUnavailable
from channel.auth import Caller
from channel.config import GatewaySettings
from channel.limiter import RateLimiter

TOOL_NAME = "claim_package_download"
#: Nobody has been identified yet when the ticket is spent; the ticket is the credential.
NOBODY = "00000000-0000-0000-0000-000000000000"
_GONE = {"confirmation_replayed": 410, "confirmation_expired": 410}
_PASSED_HEADERS = ("content-type", "content-disposition", "x-content-sha256")


@dataclass(frozen=True)
class DownloadResult:
    """Bytes with their headers, or a JSON error."""

    status: int
    data: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    error: dict[str, Any] | None = None


def _failed(status: int, code: str, message: str, cid: str, **headers: str) -> DownloadResult:
    return DownloadResult(status, headers=dict(headers), error={
        "error": {"code": code, "message": message, "retryable": False}, "correlation_id": cid})


class DownloadService:
    """Redeem a ticket and stream its package, audited as the person it belongs to."""

    def __init__(self, *, settings: GatewaySettings, auditor: ChannelAuditor, api: ApiClient, limiter: RateLimiter) -> None:
        self._s, self._auditor, self._api, self._limiter = settings, auditor, api, limiter

    async def serve(self, ticket: str, caller: Caller | None, client_address: str) -> DownloadResult:
        """The package for `ticket`, or the reason it cannot be had."""
        cid = uuid.uuid4().hex
        allowed, wait = self._limiter.allow(f"download:{client_address}")
        if not allowed:
            return _failed(429, "rate_limited", "too many download attempts", cid, **{"Retry-After": str(wait)})
        nobody = ActingUser(oid=NOBODY, tenant_id=self._s.tenant_id, display_name="download ticket",
                            channel="teams", correlation_id=cid)
        args: dict[str, Any] = {"ticket": ticket}
        if caller is not None:
            args["expected_user_oid"] = caller.acting.oid
        try:
            spent = await self._api.call_tool("claim_package_redeem", args, nobody)
        except ApiUnavailable as exc:
            return _failed(504 if exc.code == "timeout" else 502, exc.code, exc.message, cid)
        if spent.status != 200 or "facts" not in spent.body:
            code = (spent.body.get("error") or {}).get("code", "api_error")
            status = _GONE.get(code, spent.status if spent.status in (403, 404, 409) else 502)
            return _failed(status, code, "that download link cannot be used", cid)
        return await self._stream(spent.body["facts"], cid)

    @staticmethod
    def _acting_for(facts: dict[str, Any], tenant_id: str, cid: str) -> ActingUser:
        """The person a ticket was minted for, as the conversation context recorded it."""
        return ActingUser(
            oid=facts["user_oid"], tenant_id=tenant_id, display_name=facts.get("name"),
            assurance=facts.get("assurance") or "channel-asserted", channel=facts.get("channel") or "teams",
            conversation_id=facts.get("conversation_id"), correlation_id=cid,
        )

    async def _stream(self, ticket_facts: dict[str, Any], cid: str) -> DownloadResult:
        acting = self._acting_for(ticket_facts, self._s.tenant_id, cid)
        audit = AuditCall(tool_name=TOOL_NAME, action_kind="read", actor=acting,
                          args={"artifact_id": ticket_facts["artifact_id"]}, client_id=ticket_facts["client_id"])
        try:
            handle = self._auditor.begin_write(audit)
        except Exception:  # noqa: BLE001 - nothing is served that the platform cannot account for
            return _failed(503, "audit_unavailable", "the audit trail is unavailable; nothing was served", cid)
        path = f"/api/clients/{ticket_facts['client_id']}/artifacts/{ticket_facts['artifact_id']}"
        result = await self._fetch(path, acting, cid)
        outcome, error = ("ok", None) if result.status == 200 else (
            "refused" if result.status == 403 else "error", (result.error or {}).get("error", {}).get("code"))
        self._auditor.finish_write(handle, outcome, error=error)
        return result

    async def _fetch(self, path: str, acting: ActingUser, cid: str) -> DownloadResult:
        try:
            reply = await self._api.fetch(path, acting)
        except ApiUnavailable as exc:
            return _failed(504 if exc.code == "timeout" else 502, exc.code, exc.message, cid)
        if reply.status != 200:
            return _failed(404 if reply.status == 404 else 502, "download_failed", "the package could not be served", cid)
        headers = {k: v for k, v in (reply.headers or {}).items() if k.lower() in _PASSED_HEADERS}
        return DownloadResult(200, reply.raw, {**headers, "Cache-Control": "no-store", "X-Correlation-Id": cid})
