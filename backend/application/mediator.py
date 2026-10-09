"""A small mediator. Requests are data; handlers are functions; nothing else.

Why this exists at all, given that a router could simply call a function:

**Commands and queries are different, and the difference is worth enforcing.**
A query computes and returns; a command changes what the business believes.
Recording that a client claims a credit for a tax year is a decision that lands
on a filed return, and it needs an actor, a timestamp and the rule versions it
was made under. A query needs none of those. Separating them at the type level
means the write path cannot quietly acquire a read's casualness.

**Cross-cutting concerns get one home.** Timing, logging, tenant checks and the
audit trail are the same on every write. Without a pipeline they are copied into
every handler, which is where they drift and eventually get forgotten in the one
place it mattered.

**Routers stop being a place where logic hides.** A router that calls
`mediator.send(...)` and serialises the result cannot accumulate business rules
by accident, and business rules in routers is how the same statutory quantity
ended up with three implementations that disagreed.

Deliberately not a framework. No auto-discovery, no decorators, no container —
those hide the wiring, and the wiring is what a new engineer needs to read
first. Registration is explicit and lives in one file.

    result = mediator.send(GetProximityQuery(tax_year=2023, state="GA"))

THE PIPELINE, AND WHAT IS NOT IN IT
-----------------------------------

A command runs Validation -> Handler -> Audit, and every dispatch is timed.
That is the whole list. Two further stages are frequently described as being
here and are NOT:

* **Authorization** — there is no identity to authorize. Every request today
  arrives unauthenticated.
* **TenantScope** — there is no employer binding to scope to.

Both are gated on Entra (see SECURITY.md). They are absent rather than
stubbed ON PURPOSE: a stage that runs and always passes reads as a control, and
the first person to audit this would find a name where an enforcement should
be. When identity lands, they become real stages here and this paragraph goes.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Protocol, TypeVar

logger = logging.getLogger(__name__)

TResult = TypeVar("TResult")


class Request(Protocol):
    """Marker for anything the mediator can dispatch."""


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
    """

    actor: str = "system"


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
    """A bounded in-memory trail.

    IN MEMORY IS NOT THE DESTINATION. It is bounded and dies with the process,
    so it survives a support question and nothing more; the durable trail is
    `tcc_ops.agent_action_audit` plus the per-run manifest. This exists so the
    pipeline stage is real now rather than pending a store.
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

    def __init__(self, audit: AuditLog | None = None) -> None:
        self._handlers: dict[type, Handler] = {}
        self.audit = audit if audit is not None else AuditLog()

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

    def send(self, request: Any) -> Any:
        """Validation → Handler → Audit, timed. See the module docstring for
        the two stages this deliberately does not have."""
        handler = self._handlers.get(type(request))
        if handler is None:
            raise HandlerNotRegistered(
                f"No handler for {type(request).__name__}. Register it in "
                f"application/wiring.py."
            )

        is_command = isinstance(request, Command)

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
