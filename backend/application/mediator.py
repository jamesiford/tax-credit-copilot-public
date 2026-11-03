"""A small mediator. Requests are data; handlers are functions; nothing else.

Why this exists at all, given that a router could simply call a function:

**Commands and queries are different, and the difference is worth enforcing.**
A query computes and returns; a command changes what the business believes, and
needs an actor, a timestamp and the rule versions it was made under. Separating
them at the type level means the write path cannot quietly acquire a read's
casualness.

**Cross-cutting concerns get one home.** Timing, logging, authorization and the
audit trail are the same on every write; copied into handlers they drift and get
forgotten in the one place it mattered. **Routers stop being a place where logic
hides:** a router that calls `mediator.send(...)` cannot accumulate business
rules by accident.

Deliberately not a framework. No auto-discovery, no decorators, no container —
registration is explicit and lives in one file (`application/wiring.py`).

    result = mediator.send(GetProximityQuery(tax_year=2023, state="GA"))

THE PIPELINE, AND WHAT IS NOT IN IT
-----------------------------------

A command runs Authorization -> Validation -> Handler -> Audit, and every
dispatch is timed.

* **Authorization** (CH-04). A command class may declare `policy = Policy.WRITER`;
  the stage asks the configured authorizer whether the caller's PERSON — for the
  channel gateway, the user it acts for — is entitled. A policy on a mediator
  with no authorizer is REFUSED, not waved through: a control that silently does
  not run is the failure this stage exists to prevent. A refusal is recorded as
  `refused`. The caller is the `principal` argument, else the one the API guard
  set for the request, so a router that forgets it cannot demote an agent.
* **TenantScope** is still NOT here: there is no employer binding to scope to,
  and a stage that runs and always passes reads as a control.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar, Deque, Protocol, TypeVar

from application.identity import ANONYMOUS, NotAuthorized, Policy, Principal, ambient_principal

logger = logging.getLogger(__name__)

TResult = TypeVar("TResult")


class Request(Protocol):
    """Marker for anything the mediator can dispatch."""


class Authorizer(Protocol):
    """The Authorization stage's port: raise `NotAuthorized` or return."""

    def check(self, request: Any, principal: Principal) -> None: ...


@dataclass(frozen=True)
class Query:
    """A read. Computes and returns; changes nothing.

    Frozen because a handler that mutates its own request makes a retry behave
    differently from the first attempt.
    """


@dataclass(frozen=True)
class Command:
    """A write. Changes what the business believes to be true.

    Every command carries `actor` — who is responsible. On a system whose
    outputs land on tax returns, an unattributed state change is not an audit
    trail, it is a rumour.

    `policy` is what the Authorization stage demands of the caller; `None`
    leaves the command open to any authenticated caller, as before.
    """

    actor: str = "system"
    policy: ClassVar[Policy | None] = None


#: What `actor` falls back to. An audit record says so rather than presenting a
#: default as a person, because "system" in an actor column looks like a
#: service account somebody could go and ask about.
UNATTRIBUTED = "system"


@dataclass(frozen=True)
class AuditRecord:
    """One attempted write, recorded whether or not it succeeded.

    A failed write is the more interesting half: "somebody tried to resolve this
    finding and it errored" is a question that gets asked, and a trail that only
    holds successes cannot answer it.
    """

    request: str
    actor: str
    attributed: bool
    at: str
    elapsed_ms: float
    outcome: str
    error: str | None = None


class AuditLog:
    """A bounded in-memory trail: a support aid, not the destination. It dies with
    the process; the durable trails are `tcc_ops.agent_action_audit`,
    `tcc_ops.channel_audit` and the per-run manifest.
    """

    def __init__(self, limit: int = 2000) -> None:
        self._records: Deque[AuditRecord] = deque(maxlen=limit)

    def record(self, entry: AuditRecord) -> None:
        self._records.append(entry)

    @property
    def records(self) -> list[AuditRecord]:
        return list(self._records)


Handler = Callable[[Any], Any]


class HandlerNotRegistered(LookupError):
    """Raised when nothing can handle a request.

    Its own type so a caller can tell a wiring mistake from a domain failure.
    """


class Mediator:
    """Routes a request to its handler and runs the pipeline around it.

    Not thread-safe for registration — register everything at startup, then
    dispatch. Dispatch itself holds no state.
    """

    def __init__(self, audit: AuditLog | None = None, authorizer: Authorizer | None = None) -> None:
        self._handlers: dict[type, Handler] = {}
        self.audit = audit if audit is not None else AuditLog()
        self._authorizer = authorizer

    def register(self, request_type: type, handler: Handler) -> None:
        """Bind one request type to one handler.

        Re-registering raises rather than replacing. A silent overwrite means
        two modules each believe they own a request, and which one wins depends
        on import order — a bug that appears only under some entry points.
        """
        if request_type in self._handlers:
            raise ValueError(
                f"{request_type.__name__} already has a handler "
                f"({self._handlers[request_type].__name__}). Two handlers for one "
                f"request resolve by import order, which is not a decision."
            )
        self._handlers[request_type] = handler

    def send(self, request: Any, principal: Principal | None = None) -> Any:
        """Authorization → Validation → Handler → Audit, timed (see the module docstring)."""
        handler = self._handlers.get(type(request))
        if handler is None:
            raise HandlerNotRegistered(
                f"No handler for {type(request).__name__}. Register it in "
                f"application/wiring.py."
            )

        is_command = isinstance(request, Command)
        self._authorize(request, principal or ambient_principal() or ANONYMOUS, is_command)

        # Validation runs BEFORE the audit clock starts: a malformed request was
        # never a write, and recording it as an attempted one would put noise in
        # the trail that matters.
        validate = getattr(request, "validate", None)
        if callable(validate):
            validate()

        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        try:
            result = handler(request)
        except Exception as failure:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s failed: %s", "command" if is_command else "query",
                type(request).__name__,
            )
            if is_command:
                # A failed write is the half that gets asked about.
                self._audit(request, started_at, elapsed_ms, "error", failure)
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        if is_command:
            self._audit(request, started_at, elapsed_ms, "ok", None)
            logger.info(
                "command %s by %s in %.0fms",
                type(request).__name__, getattr(request, "actor", "unknown"), elapsed_ms,
            )
        else:
            logger.debug("query %s in %.0fms", type(request).__name__, elapsed_ms)
        return result

    def _authorize(self, request: Any, principal: Principal, is_command: bool) -> None:
        """Refuse before anything runs, and say so in the trail."""
        if getattr(type(request), "policy", None) is None:
            return
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            if self._authorizer is None:
                raise NotAuthorized(
                    f"{type(request).__name__} declares a policy and this mediator has no authorizer"
                )
            self._authorizer.check(request, principal)
        except NotAuthorized as refusal:
            logger.warning("refused %s: %s", type(request).__name__, refusal)
            if is_command:
                self._audit(request, started_at, 0.0, "refused", refusal)
            raise

    def _audit(
        self, request: Any, at: str, elapsed_ms: float, outcome: str,
        failure: Exception | None,
    ) -> None:
        actor = getattr(request, "actor", UNATTRIBUTED) or UNATTRIBUTED
        self.audit.record(AuditRecord(
            request=type(request).__name__,
            actor=actor,
            # Stated, not inferred later from the string: "system" is what an
            # unset actor looks like, and a reader cannot tell that from a
            # service account that genuinely made the change.
            attributed=actor != UNATTRIBUTED,
            at=at,
            elapsed_ms=elapsed_ms,
            outcome=outcome,
            error=None if failure is None else f"{type(failure).__name__}: {failure}",
        ))

    @property
    def registered(self) -> list[str]:
        """Registered request types, for diagnostics and tests."""
        return sorted(t.__name__ for t in self._handlers)
