"""Who is calling the gateway, and for whom. [CH-06]

Two token shapes are accepted and they never mix:

- **Agent** — an app-only token (the Foundry orchestrator). It must hold the app role
  `Channel.Invoke`, or, where the role cannot be assigned (a sandbox), its app id must
  be on `CHANNEL_ALLOWED_CALLER_APP_IDS`. The role is preferred and the path that
  authorised each call is logged. The person it acts for arrives in `X-Acting-*`
  headers and is an ASSERTION by a trusted service, so the audit says
  `channel-asserted`.
- **Delegated** — a user's own token with the scope `Channel.Access` (Cowork). The
  acting user IS the token's subject and any acting-user header is ignored: a person
  cannot name somebody else.

Anything else is refused with a stable JSON error: 401 for no proof of identity,
403 for proof without permission, 400 for acting-user headers that do not parse.
Tokens and headers are never logged.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from application.identity import ActingUser
from channel.config import GUID, GatewaySettings
from infrastructure.auth.entra import AuthenticationFailed, EntraTokenValidator

log = logging.getLogger("tcc.channel.auth")

ROLE_INVOKE = "Channel.Invoke"
SCOPE_ACCESS = "Channel.Access"
AGENT_CHANNELS = ("teams", "m365-copilot")
_FIELD_LIMIT = 256
_CORRELATION = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class AuthFailure(Exception):
    """A caller the gateway refuses. `status` is 400, 401 or 403; `code` is stable."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class Caller:
    """An authenticated caller and the person the call is for.

    `authorised_by` is which rule let the call in (`role`, `allow-list` or `scope`);
    `app_id` is the calling application, for the agent shapes.
    """

    acting: ActingUser
    kind: str
    authorised_by: str
    app_id: str | None = None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    return value.strip() if value and value.strip() else None


def _bearer(headers: Mapping[str, str]) -> str | None:
    scheme, _, token = (headers.get("authorization") or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _guid(value: str | None, label: str) -> str:
    if not value or not GUID.match(value):
        raise AuthFailure(400, "invalid_acting_user", f"{label} must be a GUID")
    return str(uuid.UUID(value))


def _text(value: str | None, label: str, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise AuthFailure(400, "invalid_acting_user", f"{label} is required")
        return None
    if len(value) > _FIELD_LIMIT:
        raise AuthFailure(400, "invalid_acting_user", f"{label} is longer than {_FIELD_LIMIT} characters")
    return value


def _correlation(headers: Mapping[str, str]) -> str:
    supplied = _header(headers, "x-correlation-id")
    if supplied is None:
        return uuid.uuid4().hex
    if not _CORRELATION.match(supplied):
        raise AuthFailure(400, "invalid_correlation_id", "X-Correlation-Id must be 1-64 letters, digits, . _ -")
    return supplied


def _is_app_token(claims: Mapping[str, Any]) -> bool:
    named = bool(claims.get("preferred_username") or claims.get("upn") or claims.get("name"))
    return claims.get("idtyp") == "app" or (
        bool(claims.get("oid")) and claims.get("oid") == claims.get("sub") and not named
    )


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value) if isinstance(value, (list, tuple)) else ()


class CallerAuthenticator:
    """Turn a request's headers into a `Caller`, or raise `AuthFailure`."""

    def __init__(self, settings: GatewaySettings, validator: EntraTokenValidator) -> None:
        self._settings, self._validator = settings, validator

    def authenticate(self, headers: Mapping[str, str], *, conversation_id: str | None = None) -> Caller:
        """`headers` are lower-cased. `conversation_id` (an MCP session) outranks the header."""
        try:
            claims = self._validator.claims(_bearer(headers))
        except AuthenticationFailed as exc:
            raise AuthFailure(401, "unauthenticated", str(exc)) from exc
        scopes, roles = tuple(str(claims.get("scp", "")).split()), _strings(claims.get("roles"))
        if _is_app_token(claims):
            caller = self._agent(claims, headers, scopes, roles, conversation_id)
        else:
            caller = self._delegated(claims, headers, scopes, roles, conversation_id)
        log.info("caller authorised: kind=%s via=%s", caller.kind, caller.authorised_by)
        return caller

    def _agent(self, claims, headers, scopes, roles, conversation_id) -> Caller:
        if scopes:
            raise AuthFailure(403, "mixed_token", "an app-only token must not carry delegated scopes")
        app_id = str(claims.get("azp") or claims.get("appid") or "").lower() or None
        if ROLE_INVOKE in roles:
            via = "role"
        elif app_id and app_id in self._settings.allowed_caller_app_ids:
            via = "allow-list"
        else:
            raise AuthFailure(403, "caller_not_allowed", f"the caller holds neither the '{ROLE_INVOKE}' role nor an allowed app id")
        return Caller(self._asserted_user(headers, conversation_id), "agent", via, app_id)

    def _asserted_user(self, headers: Mapping[str, str], conversation_id: str | None) -> ActingUser:
        tenant = _guid(_header(headers, "x-acting-tenant"), "X-Acting-Tenant")
        if tenant != self._settings.tenant_id:
            raise AuthFailure(403, "tenant_mismatch", "the acting user is from another tenant")
        channel = _header(headers, "x-channel")
        if channel not in AGENT_CHANNELS:
            raise AuthFailure(400, "invalid_acting_user", f"X-Channel must be one of {', '.join(AGENT_CHANNELS)}")
        return ActingUser(
            oid=_guid(_header(headers, "x-acting-user-oid"), "X-Acting-User-Oid"), tenant_id=tenant,
            display_name=_text(_header(headers, "x-acting-user-name"), "X-Acting-User-Name", required=True),
            assurance="channel-asserted", channel=channel,
            conversation_id=conversation_id or _text(_header(headers, "x-conversation-id"), "X-Conversation-Id", required=True),
            correlation_id=_correlation(headers),
        )

    def _delegated(self, claims, headers, scopes, roles, conversation_id) -> Caller:
        if SCOPE_ACCESS not in scopes:
            raise AuthFailure(403, "missing_scope", f"the token lacks the '{SCOPE_ACCESS}' scope")
        if ROLE_INVOKE in roles:
            raise AuthFailure(403, "mixed_token", "a delegated token must not carry an agent role")
        tenant = str(claims.get("tid") or "").lower()
        if tenant != self._settings.tenant_id or not claims.get("oid"):
            raise AuthFailure(403, "tenant_mismatch", "the token is not from this tenant or names no user")
        acting = ActingUser(
            oid=_guid(str(claims["oid"]), "oid"), tenant_id=tenant, display_name=claims.get("name"),
            upn=claims.get("preferred_username") or claims.get("upn"), assurance="delegated", channel="cowork",
            conversation_id=conversation_id or _header(headers, "x-conversation-id"),
            correlation_id=_correlation(headers),
        )
        return Caller(acting, "delegated", "scope", str(claims.get("azp") or "").lower() or None)
