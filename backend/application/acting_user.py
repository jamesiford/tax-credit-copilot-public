"""Read the `X-TCC-Acting-User` header an agent principal sends. [CH-04]

The channel gateway authenticates to the API as itself (an app-only token) and
says WHO it is acting for in this header. The header is therefore an assertion
by a trusted service, not proof by the person — `ActingUser.assurance` carries
that distinction into every audit row.

The value is base64url-encoded JSON, because a display name can hold characters
a raw header cannot. It is parsed strictly: a malformed, oversized or
cross-tenant header is refused rather than repaired, since a lenient parser here
decides whose name goes on a filed return.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import uuid
from typing import Any

from application.identity import ActingUser
from domain.channel import CHANNELS

HEADER = "X-TCC-Acting-User"

#: Generous for a name and a few ids, small enough that nobody smuggles a payload.
MAX_HEADER_BYTES = 2048

_FIELD_LIMIT = 256
_ASSURANCES = frozenset({"channel-asserted", "delegated"})
_OPTIONAL = ("name", "upn", "channel", "conversation_id", "correlation_id")


class ActingUserError(ValueError):
    """The header is absent where required, malformed, or names the wrong tenant. Routers map it to 400."""


def encode(payload: dict[str, Any]) -> str:
    """The sender's half, kept beside the parser so the two cannot drift."""
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> dict[str, Any]:
    if len(value.encode("utf-8", "ignore")) > MAX_HEADER_BYTES:
        raise ActingUserError("acting-user header is too large")
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ActingUserError("acting-user header is not base64url")
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ActingUserError("acting-user header is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ActingUserError("acting-user header must be a JSON object")
    return payload


def _guid(value: Any, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ActingUserError(f"acting-user {label} must be a GUID") from exc


def _text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > _FIELD_LIMIT:
        raise ActingUserError(f"acting-user {key} must be a string of at most {_FIELD_LIMIT} characters")
    return value.strip() or None


def parse_acting_user(value: str | None, tenant_id: str) -> ActingUser:
    """The person named by the header, or `ActingUserError`.

    `tid` must equal the tenant this API trusts: a gateway cannot vouch for a
    person from another directory.
    """
    if not value or not value.strip():
        raise ActingUserError("an agent request must name the user it acts for")
    payload = _decode(value.strip())
    if _guid(payload.get("tid"), "tid") != _guid(tenant_id, "configured tenant"):
        raise ActingUserError("acting-user tid does not match the configured tenant")
    assurance = _text(payload, "assurance") or "channel-asserted"
    if assurance not in _ASSURANCES:
        raise ActingUserError("acting-user assurance is not recognised")
    fields = {key: _text(payload, key) for key in _OPTIONAL}
    if fields["channel"] is not None and fields["channel"] not in CHANNELS:
        raise ActingUserError(f"acting-user channel must be one of {', '.join(CHANNELS)}")
    return ActingUser(
        oid=_guid(payload.get("oid"), "oid"),
        tenant_id=_guid(payload["tid"], "tid"),
        display_name=fields["name"],
        upn=fields["upn"],
        assurance=assurance,
        channel=fields["channel"],
        conversation_id=fields["conversation_id"],
        correlation_id=fields["correlation_id"],
    )
