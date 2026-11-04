"""The channel auditor: a durable record of every tool call, per user. [CH-03, ADR-008]

A read writes one `single` event. A write writes a `begin` event (outcome
`pending`) BEFORE anything changes and an `end` event after, so a process that
dies between the two still leaves a record — `domain.channel.collapse` reports
it as `pending`. `audited(...)` guarantees the `end` event even when the work
raises, and says `refused` when it was an authorization refusal rather than a
fault, because "somebody tried and was refused" and "it broke" are different
questions.

If the opening event cannot be written, the call does not proceed: an action the
platform cannot account for is not performed. A failure to write the closing
event does not mask the result, because the `begin` row is already there to say
the request started. Both raise the `audit_write_failed` alert
(`application.audit_alert`), so a failure is never silent: the first refuses the
call, the second only raises the alarm.

The request summary is for a human reading a timeline. It DROPS any key that
names payroll or an employee, truncates what is left, and is never the request
itself — the request is represented by its SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from application.audit_alert import audit_write_failed
from application.identity import ActingUser, NotAuthorized
from domain.channel import (
    ERROR_LIMIT, SUMMARY_LIMIT, ChannelAuditEvent, ChannelAuditRepository, utcnow,
)

log = logging.getLogger("tcc.channel_audit")

#: Key names that never reach a summary. An employee handle is dropped too: the
#: record token is opaque, but a timeline is read by people and logged by tools.
SENSITIVE_KEY = re.compile(
    r"employee|ssn|social|payroll|wage|salary|record_token|token|password|secret|birth|dob",
    re.IGNORECASE,
)
_VALUE_LIMIT = 80
#: How the diagnostic log names the event that failed to write.
_ROLE = {"begin": "opening", "end": "closing"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def request_sha256(args: Mapping[str, Any]) -> str:
    """The identity of a request, over everything in it, without keeping any of it."""
    return hashlib.sha256(_canonical(dict(args)).encode("utf-8")).hexdigest()


def _render(value: Any) -> str:
    if isinstance(value, Mapping):
        return "{" + _pairs(value) + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        return f"[{len(value)} items]"
    return str(value)[:_VALUE_LIMIT]


def _pairs(args: Mapping[str, Any]) -> str:
    kept = [(k, v) for k, v in sorted(args.items(), key=lambda kv: str(kv[0]))
            if not SENSITIVE_KEY.search(str(k)) and v is not None]
    return ", ".join(f"{k}={_render(v)}" for k, v in kept)


def summarise_request(args: Mapping[str, Any], limit: int = SUMMARY_LIMIT) -> str:
    """`key=value` pairs, sensitive keys dropped, long values and the whole line truncated."""
    text = _pairs(args)
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class AuditCall:
    """What is being audited. `args` is hashed and summarised, never stored.

    `summary` replaces `args` as what the human-readable line is drawn from, for a call whose
    arguments need a purpose-built description (a data query names columns and operators, and
    values only where the model says they are not sensitive).
    """

    tool_name: str
    action_kind: str
    actor: ActingUser | None = None
    args: Mapping[str, Any] = field(default_factory=dict)
    client_id: int | None = None
    tax_year: int | None = None
    confirmation_ref: str | None = None
    is_deterministic_path: bool = True
    summary: Mapping[str, Any] | None = None


@dataclass
class AuditHandle:
    """An open request. The caller fills in what it learned before it closes."""

    audit_id: str
    call: AuditCall
    correlation_id: str
    began_at: datetime
    outcome: str | None = None
    run_id: str | None = None
    trail_sha256: str | None = None
    numeric_guard: str = "n/a"
    confirmation_ref: str | None = None

    def annotate(self, **result: Any) -> None:
        for name, value in result.items():
            if not hasattr(self, name) or name in ("audit_id", "call", "began_at"):
                raise AttributeError(f"cannot annotate {name!r}")
            setattr(self, name, value)


class ChannelAuditor:
    def __init__(
        self, repository: ChannelAuditRepository,
        clock: Callable[[], datetime] = utcnow,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._new_id = new_id

    # ------------------------------------------------------------------ events

    def _event(
        self, handle: AuditHandle, *, phase: str, seq: int, outcome: str, error: str | None = None,
    ) -> ChannelAuditEvent:
        call, actor, now = handle.call, handle.call.actor or ActingUser(oid="anonymous"), self._clock()
        return ChannelAuditEvent(
            audit_id=handle.audit_id, event_seq=seq, phase=phase,
            correlation_id=handle.correlation_id, occurred_at=now,
            elapsed_ms=None if phase == "begin" else int((now - handle.began_at).total_seconds() * 1000),
            channel=actor.channel or "api-test", user_oid=actor.oid, tenant_id=actor.tenant_id,
            user_display_name=actor.display_name, user_upn=actor.upn,
            identity_assurance=actor.assurance, conversation_id=actor.conversation_id,
            tool_name=call.tool_name, action_kind=call.action_kind,
            client_id=call.client_id, tax_year=call.tax_year,
            request_summary=None if phase == "end" else summarise_request(
                call.args if call.summary is None else call.summary),
            request_sha256=request_sha256(call.args),
            confirmation_ref=handle.confirmation_ref or call.confirmation_ref,
            outcome=outcome, error=(error or None) and error[:ERROR_LIMIT],
            run_id=handle.run_id, trail_sha256=handle.trail_sha256,
            numeric_guard=handle.numeric_guard,
            is_deterministic_path=call.is_deterministic_path,
        )

    def _open(self, call: AuditCall) -> AuditHandle:
        actor = call.actor
        return AuditHandle(
            audit_id=self._new_id(),
            call=call,
            correlation_id=(actor.correlation_id if actor else None) or self._new_id(),
            began_at=self._clock(),
        )

    # ------------------------------------------------------------------- reads

    def record_read(self, call: AuditCall, outcome: str = "ok", *, error: str | None = None,
                    **result: Any) -> str:
        """One `single` event. Returns the audit id."""
        handle = self._open(call)
        handle.annotate(**result)
        self._append(lambda: self._event(handle, phase="single", seq=1, outcome=outcome, error=error), "read", fatal=True)
        return handle.audit_id

    # ------------------------------------------------------------------ writes

    def begin_write(self, call: AuditCall) -> AuditHandle:
        """Write the `pending` event. Raises if it cannot: nothing proceeds unrecorded."""
        handle = self._open(call)
        self._append(lambda: self._event(handle, phase="begin", seq=1, outcome="pending"), "begin", fatal=True)
        return handle

    def finish_write(self, handle: AuditHandle, outcome: str, *, error: str | None = None,
                     **result: Any) -> None:
        """Write the `end` event. A failure raises the alert and does not mask the result:
        the `begin` row already says the request started."""
        handle.annotate(**result)
        self._append(lambda: self._event(handle, phase="end", seq=2, outcome=outcome, error=error), "end", fatal=False)

    def _append(self, make: Callable[[], ChannelAuditEvent], operation: str, *, fatal: bool) -> None:
        """Build and write one event. A failure raises the alert here, once, and propagates when `fatal`."""
        try:
            self._repository.append(make())
        except Exception as exc:
            log.exception("could not write the %s channel audit event", _ROLE.get(operation, operation))
            audit_write_failed("channel_audit", operation, exc, fatal=fatal)
            if fatal:
                raise

    # -------------------------------------------------------------- the wrapper

    @contextmanager
    def audited(self, call: AuditCall) -> Iterator[AuditHandle]:
        """Guarantee a closing event, whatever the work does.

        Reads (and `narrate`, which changes nothing) write one event on exit;
        prepare and commit write `begin` first.
        `NotAuthorized` is `refused`; any other exception is `error`; otherwise
        the outcome the work set on the handle, else `ok`.
        """
        is_write = call.action_kind in ("write_prepare", "write_commit")
        handle = self.begin_write(call) if is_write else self._open(call)
        try:
            yield handle
        except NotAuthorized as exc:
            self._close(handle, "refused", str(exc), is_write)
            raise
        except Exception as exc:
            self._close(handle, "error", f"{type(exc).__name__}: {exc}", is_write)
            raise
        self._close(handle, handle.outcome or "ok", None, is_write)

    def _close(self, handle: AuditHandle, outcome: str, error: str | None, is_write: bool) -> None:
        if is_write:
            self.finish_write(handle, outcome, error=error)
            return
        self._append(lambda: self._event(handle, phase="single", seq=1, outcome=outcome, error=error), "single", fatal=True)
