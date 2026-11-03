"""One pipeline for every tool call, whichever door it came in by. [CH-06]

REST (`/channel/v1/tools/{tool}`) and MCP (`/mcp`) both end here, so a call is
audited, rate-limited, entitled and forwarded identically and the two cannot drift.

What is audited, and by whom (no double audit):

- A **read** is audited here: a `begin` event before the call and an `end` event
  after, always, whatever the outcome.
- A **write** (`*_prepare`, `*_commit`) is audited by the capability itself, inside
  the API, with its confirmation reference. The gateway adds ONE event only for what
  the capability cannot see: a refusal or fault before it ran (the rate limit, the
  gateway's own writer check, the API unreachable, a timeout, a request the API
  rejected before dispatch). Each carries the same correlation id.

If the opening event of a read cannot be written, the call does not proceed: a call
the platform cannot account for is not made. A refusal's event that cannot be
written is logged and does not mask the refusal.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from application.capabilities import catalog
from application.capabilities.envelope import ToolResult
from application.channel_audit import AuditCall, ChannelAuditor
from channel.api_client import ApiClient, ApiResult, ApiUnavailable
from channel.auth import Caller
from channel.config import GatewaySettings
from channel.ledger import FactLedger, verify_against
from channel.limiter import RateLimiter
from channel.tools import PING_SPEC, check_arguments, client_and_year, offered_tools

log = logging.getLogger("tcc.channel.pipeline")

#: Failures the API raises before it dispatches to a capability: the capability's
#: own audit never saw them, so the gateway records them for a write.
BEFORE_CAPABILITY = frozenset({
    "invalid_arguments", "unknown_tool", "not_implemented", "gateway_local", "client_not_authorized", "timeout",
    "api_unreachable", "bad_response", "api_error",
})
_PING_HEADERS = ("x-acting-user-oid", "x-acting-user-name", "x-acting-tenant", "x-channel", "x-conversation-id", "x-correlation-id")


@dataclass(frozen=True)
class ToolCall:
    """A tool call as it arrives: arguments, the commit's two fields, and the raw headers (ping only)."""

    args: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    """What goes back to the caller: a status, a JSON body and any headers."""

    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


def error_outcome(
    status: int, code: str, message: str, correlation_id: str, *, retryable: bool = False,
    headers: dict[str, str] | None = None, **extra: Any,
) -> Outcome:
    """The stable error body, with the correlation id a reader quotes to support."""
    error = {"code": code, "message": message, "retryable": retryable, **extra}
    return Outcome(status, {"error": error, "correlation_id": correlation_id}, headers or {})


class ToolPipeline:
    """Authenticated caller + tool + arguments in, audited outcome out."""

    def __init__(
        self, *, settings: GatewaySettings, auditor: ChannelAuditor, entitlement: Any, limiter: RateLimiter,
        ledger: FactLedger, api: ApiClient, version: str,
    ) -> None:
        self._s, self._auditor, self._entitlement = settings, auditor, entitlement
        self._limiter, self._ledger, self._api, self._version = limiter, ledger, api, version

    async def run(self, caller: Caller, tool: str, call: ToolCall) -> Outcome:
        """Run `tool` for `caller`. Never raises: every failure is an `Outcome`."""
        acting = caller.acting
        spec = next((t for t in offered_tools(self._s) if t.name == tool), None)
        if spec is None:
            return error_outcome(404, "unknown_tool", f"no such tool: {tool}", acting.correlation_id or "")
        audit_call = AuditCall(
            tool_name=tool, action_kind=spec.kind, actor=acting, args=_audited_args(call),
            **dict(zip(("client_id", "tax_year"), client_and_year(call.args))),
        )
        refused = await self._refuse_early(spec, audit_call)
        if refused is not None:
            return refused
        if spec.kind == catalog.READ:
            return await self._read(spec, caller, call, audit_call)
        return await self._write(spec, caller, call, audit_call)

    # ---------------------------------------------------------------- early refusals

    async def _refuse_early(self, spec: catalog.CapabilitySpec, audit: AuditCall) -> Outcome | None:
        acting, cid = audit.actor, audit.actor.correlation_id or ""
        allowed, wait = self._limiter.allow(acting.oid)
        if not allowed:
            self._single(audit, "refused", "rate_limited")
            return error_outcome(429, "rate_limited", "too many calls; slow down", cid, retryable=True,
                                 headers={"Retry-After": str(wait)}, retry_after_seconds=wait)
        if spec.kind == catalog.WRITE_COMMIT and not await self._is_writer(acting.oid):
            self._single(audit, "refused", "not entitled to make changes")
            return error_outcome(403, "not_authorized", "this user is not entitled to make changes", cid)
        return None

    async def _is_writer(self, oid: str) -> bool:
        try:
            return bool(await asyncio.to_thread(self._entitlement.is_writer, oid))
        except Exception as exc:  # noqa: BLE001 - an entitlement that cannot answer denies
            log.warning("writer check failed, denying: %s", type(exc).__name__)
            return False

    def _single(self, audit: AuditCall, outcome: str, error: str, **result: Any) -> None:
        try:
            self._auditor.record_read(audit, outcome, error=error, **result)
        except Exception:  # noqa: BLE001 - the refusal stands even if its record could not be written
            log.exception("could not write the gateway audit event for %s", audit.tool_name)

    # ------------------------------------------------------------------------ reads

    async def _read(self, spec: catalog.CapabilitySpec, caller: Caller, call: ToolCall, audit: AuditCall) -> Outcome:
        cid = audit.actor.correlation_id or ""
        try:
            handle = self._auditor.begin_write(audit)
        except Exception:  # noqa: BLE001
            log.exception("could not open the audit record; the call is not made")
            return error_outcome(503, "audit_unavailable", "the audit trail is unavailable; nothing was done", cid, retryable=True)
        status, body, local = await self._execute(spec, caller, call)
        outcome, error = _judge(status, body)
        result = _provenance(body)
        if local and spec.name == "verify_figures" and status == 200:
            result["numeric_guard"] = body["facts"]["status"]
        self._auditor.finish_write(handle, outcome, error=error, **result)
        return self._shaped(spec, caller, status, body)

    # ----------------------------------------------------------------------- writes

    async def _write(self, spec: catalog.CapabilitySpec, caller: Caller, call: ToolCall, audit: AuditCall) -> Outcome:
        status, body, _ = await self._execute(spec, caller, call)
        if status != 200 and (body.get("error") or {}).get("code") in BEFORE_CAPABILITY:
            outcome, error = _judge(status, body)
            self._single(audit, outcome, error or "failed before the capability ran")
        return self._shaped(spec, caller, status, body)

    # -------------------------------------------------------------------- executing

    async def _execute(self, spec: catalog.CapabilitySpec, caller: Caller, call: ToolCall) -> tuple[int, dict[str, Any], bool]:
        """`(status, body, answered_locally)`. The body is an envelope or `{"error": ...}`."""
        if catalog.GATEWAY_LOCAL in spec.tags:
            return (*await self._local(spec, caller, call), True)
        try:
            reply = await self._api.call_tool(
                spec.name, dict(call.args), caller.acting,
                idempotency_key=call.idempotency_key, confirmation_token=call.confirmation_token,
            )
        except ApiUnavailable as exc:
            status = 504 if exc.code == "timeout" else 502
            return status, {"error": {"code": exc.code, "message": exc.message, "retryable": True}}, False
        return (*_api_reply(reply), False)

    async def _local(self, spec: catalog.CapabilitySpec, caller: Caller, call: ToolCall) -> tuple[int, dict[str, Any]]:
        problem = check_arguments(spec, call.args)
        if problem:
            return 422, {"error": {"code": "invalid_arguments", "message": problem, "retryable": False}}
        if spec.name == "verify_figures":
            key = _conversation_key(caller)
            result = verify_against(self._ledger, key, call.args["draft_text"], list(call.args.get("allowed_context", [])))
            return 200, result.to_dict()
        return 200, await self._ping(caller, call)

    async def _ping(self, caller: Caller, call: ToolCall) -> dict[str, Any]:
        facts = {
            "gateway_version": self._version, "caller_shape": caller.kind, "authorised_by": caller.authorised_by,
            "acting_user_received": {h: call.headers.get(h) for h in _PING_HEADERS if h in call.headers},
            "acting_user_resolved": {"oid": caller.acting.oid, "tenant_id": caller.acting.tenant_id,
                                     "channel": caller.acting.channel, "assurance": caller.acting.assurance},
            "api_reachable": await self._api.reachable(caller.acting),
        }
        return ToolResult(tool=PING_SPEC.name, facts=facts).to_dict()

    # ---------------------------------------------------------------------- shaping

    def _shaped(self, spec: catalog.CapabilitySpec, caller: Caller, status: int, body: dict[str, Any]) -> Outcome:
        cid = caller.acting.correlation_id or ""
        if status == 200 and "facts" in body:
            self._ledger.record(_conversation_key(caller), spec.name, body["facts"])
        return Outcome(status, {**body, "correlation_id": cid})


def _conversation_key(caller: Caller) -> str:
    return caller.acting.conversation_id or f"user:{caller.acting.oid}"


def _audited_args(call: ToolCall) -> dict[str, Any]:
    """What is hashed for the audit: the arguments and the commit's two fields, never kept."""
    return {**call.args, **({"idempotency_key": call.idempotency_key} if call.idempotency_key else {}),
            **({"confirmation_token": call.confirmation_token} if call.confirmation_token else {})}


def _api_reply(reply: ApiResult) -> tuple[int, dict[str, Any]]:
    """The API's envelope or error, unchanged.

    A reply with no `error` object and a non-200 status came from the API's guard
    (its credentials or subnet check), not from a capability: it says the GATEWAY is
    misconfigured, so it is a 502 here and never a 403 that would read as "you may
    not".
    """
    if reply.status == 200 or "error" in reply.body:
        return reply.status, reply.body
    message = f"the API refused the gateway's request ({reply.status}); check its role and network access"
    return 502, {"error": {"code": "api_error", "message": message, "retryable": False}}


def _judge(status: int, body: Mapping[str, Any]) -> tuple[str, str | None]:
    """`(audit outcome, error text)` for a finished call."""
    if status == 200:
        return "ok", None
    error = body.get("error") or {}
    refused = status == 403 or error.get("code") in ("not_authorized", "client_not_authorized")
    return ("refused" if refused else "error"), f"{error.get('code')}: {error.get('message')}"


def _provenance(body: Mapping[str, Any]) -> dict[str, Any]:
    prov = body.get("provenance") or {}
    return {k: prov[k] for k in ("run_id", "trail_sha256") if prov.get(k)}
