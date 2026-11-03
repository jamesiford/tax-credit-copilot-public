"""Who may run a command. [CH-04]

A command declares what it demands (`policy = Policy.WRITER`); this module is
the one place that turns the declaration into a decision, so the rule is read
in one file rather than inferred from scattered checks.

Entitlement is keyed by the PERSON's object id. For an agent principal that is
the user it acts for, never the gateway's service principal: the gateway is
trusted to carry an identity, not to hold a person's rights.

Signed-in people (`TCC.User`) and the anonymous local caller keep writing as
they always have unless `CHANNEL_ENFORCE_WRITER_FOR_USERS` is on. The channel is
new surface that reaches people who never opened the portal; the portal's
existing users are not silently locked out by shipping it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import NotAuthorized, Policy, Principal, WriterEntitlement
from application.mediator import Command


@dataclass(frozen=True)
class WriterProbe(Command):
    """A command that does nothing, declaring the writer policy.

    Lets a flow that is not itself a command (preparing a change, which writes
    nothing) ask the SAME question the mediator asks, instead of a second
    implementation of "is this person a writer" that could disagree with it.
    """

    policy = Policy.WRITER


@dataclass
class WriterPolicy:
    entitlement: WriterEntitlement
    enforce_for_users: bool = False

    def check(self, request: Any, principal: Principal) -> None:
        """Raise `NotAuthorized` unless this principal may run `request`."""
        policy = getattr(type(request), "policy", None)
        if policy is None:
            return
        if policy is not Policy.WRITER:
            raise NotAuthorized(f"unknown policy {policy!r}")
        if principal.is_agent:
            self._check_agent(request, principal)
        elif self.enforce_for_users:
            self._require_writer(principal.effective_oid)

    def _check_agent(self, request: Any, principal: Principal) -> None:
        acting = principal.acting_for
        if acting is None:
            raise NotAuthorized("an agent write must name the user it acts for")
        # A write is attributed to the person; a command naming anyone else was
        # built by code that did not take the principal, and must not land.
        author = getattr(request, "actor", None)
        if author != acting.actor:
            raise NotAuthorized("the command's author is not the user the agent acts for")
        self._require_writer(acting.oid)

    def _require_writer(self, oid: str | None) -> None:
        if not oid or not self.entitlement.is_writer(oid):
            raise NotAuthorized("this user is not entitled to make changes")
