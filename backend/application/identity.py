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

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Principal:
    oid: str | None = None
    upn: str | None = None
    name: str | None = None
    tenant_id: str | None = None
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    authenticated: bool = False

    @property
    def actor(self) -> str:
        """The identity a write is attributed to: UPN, else object id."""
        return self.upn or self.oid or "anonymous"

    def to_dict(self) -> dict:
        return {
            "authenticated": self.authenticated,
            "upn": self.upn,
            "oid": self.oid,
            "name": self.name,
            "roles": list(self.roles),
        }


#: The caller when AUTH_MODE=none. Not a user: an absence of one.
ANONYMOUS = Principal()


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
