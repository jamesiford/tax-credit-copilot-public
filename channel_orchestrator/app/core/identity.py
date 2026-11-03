"""Who is asking? Resolve it from the platform's signals, or refuse. [CH-08]

Every figure the orchestrator shows and every change it commits is attributed to a
person, so a turn with no resolvable person runs nothing: no tool, no model. The
failure is a refusal sentence, never a default user and never the agent's own
identity standing in for the person.

Which signal carries the Entra object id is NOT settled for the Teams path. The
Foundry runtime documents an opaque per-user id (`x-agent-user-id`) for every caller, an
invocation-local original-subject assertion (`x-ms-original-subject`: `oid`, `tid`,
`idtype`; an experimental draft the platform calls attribution, not proof) and a trusted
Entra identity (`x-ms-user-identity`) only when end-user delegation is authorised; whether a
Teams or Copilot Chat message arrives with any of them is a live question (Prompt 6, spike
S3). So the sources are configuration (`CHANNEL_IDENTITY_SOURCES`), the default is the two
the platform itself sets, and the resolution records WHICH source answered, so the audit row
and `/whoami` can say it. `client-headers` (`x-client-*`, caller-supplied) is opt-in.

`x-agent-user-id` is deliberately not a source: it is not an object id, the gateway
would refuse it (`X-Acting-User-Oid` must be a GUID), and inventing a mapping from it
would assert an identity nobody proved.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
NAME_UNKNOWN = "(name not provided)"
_FIELD_LIMIT = 256
#: Header names the debug report may name. Values are shown only for the three identity fields.
WATCHED = (
    "x-ms-original-subject-oid", "x-ms-original-subject-tid", "x-ms-original-subject-idtype",
    "x-ms-user-identity", "x-agent-user-id", "x-agent-foundry-call-id",
    "x-client-acting-user-oid", "x-client-acting-user-name", "x-client-tenant", "x-client-conversation-id",
)


@dataclass(frozen=True)
class ActingIdentity:
    """The person a turn is for, where we learned it, and how strongly."""

    oid: str
    name: str
    tenant_id: str
    channel: str
    conversation_id: str
    correlation_id: str
    source: str

    @property
    def key(self) -> tuple[str, str]:
        """State is held per person AND conversation: somebody else's `confirm` finds nothing."""
        return (self.oid, self.conversation_id)

    def gateway_headers(self) -> dict[str, str]:
        """The headers the gateway authenticates an agent caller's acting user from."""
        return {
            "X-Acting-User-Oid": self.oid, "X-Acting-User-Name": self.name, "X-Acting-Tenant": self.tenant_id,
            "X-Channel": self.channel, "X-Conversation-Id": self.conversation_id, "X-Correlation-Id": self.correlation_id,
        }


@dataclass(frozen=True)
class Refusal:
    """Why no identity could be resolved. `reason` is for the log; the reader is told `message`."""

    reason: str
    message: str = (
        "I can't tell who you are in this conversation, so I won't run anything. "
        "Every answer and every change here is recorded against a named person."
    )


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text[:_FIELD_LIMIT] if text else None


def _from_platform(signals: Mapping[str, str]) -> tuple[str, str | None, str | None] | None:
    oid = _clean(signals.get("x-ms-user-identity"))
    return (oid, _clean(signals.get("x-client-acting-user-name")), _clean(signals.get("x-client-tenant"))) if oid else None


def _from_client_headers(signals: Mapping[str, str]) -> tuple[str, str | None, str | None] | None:
    oid = _clean(signals.get("x-client-acting-user-oid"))
    return (oid, _clean(signals.get("x-client-acting-user-name")), _clean(signals.get("x-client-tenant"))) if oid else None


def _from_original_subject(signals: Mapping[str, str]) -> tuple[str, str | None, str | None] | None:
    """The platform's `x-ms-original-subject` (oid, tid), which the host flattens into synthetic signals."""
    oid = _clean(signals.get("x-ms-original-subject-oid"))
    if not oid:
        return None
    return oid, _clean(signals.get("x-client-acting-user-name")), _clean(signals.get("x-ms-original-subject-tid"))


def _from_agent_user_id(signals: Mapping[str, str]) -> tuple[str, str | None, str | None] | None:
    """The platform's `x-agent-user-id`, used only when it IS an Entra object id.

    Documented as a per-user partition key, not a credential, so it may be opaque: a value that is not a
    GUID is no signal at all (the next source is tried), never a refusal. Opt-in: whether Teams sends the
    object id here is what the live `/whoami` shape report settles. It names no tenant.
    """
    value = _clean(signals.get("x-agent-user-id"))
    return (value, _clean(signals.get("x-client-acting-user-name")), None) if value and GUID.match(value) else None


_READERS = {"original-subject": _from_original_subject, "platform": _from_platform, "client-headers": _from_client_headers,
            "agent-user-id": _from_agent_user_id}


def resolve_identity(
    signals: Mapping[str, str], *, sources: tuple[str, ...], tenant_id: str, channel: str,
    conversation_id: str | None, correlation_id: str,
) -> ActingIdentity | Refusal:
    """The acting person from the first configured source that has one, or a `Refusal`.

    `signals` are lower-cased header names to values, as the host received them. A tenant
    that is named and differs from ours refuses, as does an object id that is not a GUID:
    the gateway would refuse them too, and refusing here keeps the model and every tool
    out of a turn that cannot be attributed.
    """
    if not conversation_id:
        return Refusal("no conversation id")
    for source in sources:
        found = _READERS[source](signals)
        if found is None:
            continue
        oid, name, tenant = found
        if not GUID.match(oid):
            return Refusal(f"{source} gave an object id that is not a GUID")
        if tenant and tenant.lower() != tenant_id.lower():
            return Refusal(f"{source} names a different tenant")
        return ActingIdentity(oid.lower(), name or NAME_UNKNOWN, tenant_id.lower(), channel, conversation_id, correlation_id, source)
    return Refusal("no configured source carried an Entra object id: " + ", ".join(sources))


def describe_signals(signals: Mapping[str, str]) -> dict[str, object]:
    """For `/whoami`: which watched headers arrived, with values for the identity ones only. Never a credential."""
    shown = (
        "x-ms-original-subject-oid", "x-ms-original-subject-tid", "x-ms-original-subject-idtype",
        "x-ms-user-identity", "x-client-acting-user-oid", "x-client-acting-user-name", "x-client-tenant",
    )
    return {
        "present": [name for name in WATCHED if name in signals],
        "values": {name: signals[name] for name in shown if name in signals},
        "agent_user_id": agent_user_id_shape(signals),
    }


def agent_user_id_shape(signals: Mapping[str, str]) -> dict[str, object] | None:
    """What `x-agent-user-id` looks like, without showing it unless it is an object id.

    The question the live spike answers: is it the person's Entra object id (then `agent-user-id` can be a
    source) or an opaque key (then it cannot)? `equals_an_oid_signal` compares it with the other oid signals.
    """
    value = _clean(signals.get("x-agent-user-id"))
    if not value:
        return None
    oids = {signals[n].strip().lower() for n in ("x-ms-original-subject-oid", "x-ms-user-identity", "x-client-acting-user-oid") if signals.get(n)}
    shape: dict[str, object] = {"kind": "guid" if GUID.match(value) else "opaque", "length": len(value), "equals_an_oid_signal": value.lower() in oids}
    if shape["kind"] == "guid":
        shape["value"] = value
    return shape
