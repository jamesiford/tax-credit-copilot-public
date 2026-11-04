"""Who is asking, and which clients they may see. [AUTH-3, AUTH-4, D24]

Two small types the API and the commands share:

- `Principal` is the caller, as a validated token describes them. Under
  `AUTH_MODE=none` there is no token, so the caller is `ANONYMOUS` and says so:
  a write is then attributed to whatever the request supplied, never to a name
  the server invented.
- `ClientAuthorizer` is the port that answers "may this caller see this
  client?". v2 ships `AllClientsAuthorizer` — any holder of the `TCC.User` role
  sees every client, the internal-analyst persona — and tests prove the deny
  path with a fake. A customer that needs per-client entitlement implements the
  port; nothing else changes.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from domain.channel_trust import FIRST_PARTY_CHANNELS


class NotAuthorized(PermissionError):
    """The caller is who they say and may not do this. Routers map it to 403."""


@dataclass(frozen=True)
class ActingUser:
    """The person a channel request is made on behalf of.

    Asserted by the channel (Azure Bot Service says who sent the message), not
    proven by a token of theirs — hence `assurance`, which an audit row carries.
    """

    oid: str
    tenant_id: str | None = None
    display_name: str | None = None
    upn: str | None = None
    assurance: str = "channel-asserted"
    channel: str | None = None
    conversation_id: str | None = None
    correlation_id: str | None = None

    @property
    def is_first_party(self) -> bool:
        """Positively Teams or Copilot Chat, as the channel asserted it. The one definition both the API and the
        gateway use to decide who may be handed employee-level rows; anything else is treated like Cowork. [RM-02]"""
        return self.channel in FIRST_PARTY_CHANNELS and self.assurance == "channel-asserted"

    @property
    def actor(self) -> str:
        """What a write is attributed to: UPN, else object id."""
        return self.upn or self.oid


PRINCIPAL_USER = "user"
PRINCIPAL_AGENT = "agent"


@dataclass(frozen=True)
class Principal:
    """The caller. A `user` is a person with a delegated token; an `agent` is a
    service (the channel gateway) holding an app-only token, acting for the
    person in `acting_for`.

    An agent's own object id is never the author of a write: attributing a
    change to the gateway would say "a bot did it" about something a named
    person asked for, so `actor` follows `acting_for`.
    """

    oid: str | None = None
    upn: str | None = None
    name: str | None = None
    tenant_id: str | None = None
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    authenticated: bool = False
    principal_type: str = PRINCIPAL_USER
    acting_for: ActingUser | None = None

    @property
    def is_agent(self) -> bool:
        return self.principal_type == PRINCIPAL_AGENT

    @property
    def actor(self) -> str:
        """The identity a write is attributed to: UPN, else object id."""
        if self.is_agent:
            return self.acting_for.actor if self.acting_for else "anonymous"
        return self.upn or self.oid or "anonymous"

    @property
    def effective_oid(self) -> str | None:
        """The object id entitlements are checked against: the person, never the bot."""
        if self.is_agent:
            return self.acting_for.oid if self.acting_for else None
        return self.oid

    def as_acting_user(self) -> ActingUser | None:
        """The person this principal speaks for, in the shape an audit row carries.

        A signed-in person is `delegated`: their own token proves who they are.
        """
        if self.is_agent:
            return self.acting_for
        if not self.oid:
            return None
        return ActingUser(
            oid=self.oid, tenant_id=self.tenant_id, display_name=self.name, upn=self.upn,
            assurance="delegated",
        )

    def to_dict(self) -> dict:
        return {
            "authenticated": self.authenticated,
            "upn": self.upn,
            "oid": self.oid,
            "name": self.name,
            "roles": list(self.roles),
            "principal_type": self.principal_type,
            "acting_for": None if self.acting_for is None else {
                "oid": self.acting_for.oid,
                "name": self.acting_for.display_name,
                "upn": self.acting_for.upn,
                "assurance": self.acting_for.assurance,
                "channel": self.acting_for.channel,
            },
        }


#: The caller when AUTH_MODE=none. Not a user: an absence of one.
ANONYMOUS = Principal()

#: The principal of the request being served. Set once by the API guard so a
#: router that forgets to hand its principal to the mediator cannot turn an
#: agent into an anonymous caller: the pipeline reads this when none is passed.
_CURRENT: ContextVar[Principal | None] = ContextVar("tcc_current_principal", default=None)


def set_ambient_principal(principal: Principal | None) -> None:
    _CURRENT.set(principal)


def ambient_principal() -> Principal | None:
    return _CURRENT.get()


class Policy(Enum):
    """What a command demands of its caller, declared on the command class."""

    WRITER = "writer"


class WriterEntitlement(Protocol):
    """May this person change what the business believes? Keyed by object id."""

    def is_writer(self, user_oid: str) -> bool:
        ...


class ClientAuthorizer(Protocol):
    """May this principal act on this client? [D24]"""

    def is_authorized(self, principal: Principal, client_id: int) -> bool:
        ...


@dataclass
class AllClientsAuthorizer:
    """v2's entitlement: every authenticated `TCC.User` sees every client.

    Under `AUTH_MODE=none` there is no principal to entitle, and the startup
    check (D26) is what keeps that mode away from customer data.
    """

    def is_authorized(self, principal: Principal, client_id: int) -> bool:
        return True


@dataclass
class AllowListAuthorizer:
    """A fixed entitlement map. Used by tests to prove the deny path."""

    allowed: dict[str | None, set[int]] = field(default_factory=dict)

    def is_authorized(self, principal: Principal, client_id: int) -> bool:
        return client_id in self.allowed.get(principal.oid, set())
