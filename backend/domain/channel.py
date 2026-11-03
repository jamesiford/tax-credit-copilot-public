"""The channel's durable records and the ports that store them. [ADR-007, ADR-008]

Standard library only. Four kinds of record, all append-only in spirit:

- `ChannelAuditEvent` — one event in a request's life. A write is a `begin`
  event (outcome `pending`) and an `end` event sharing an `audit_id`, so a
  request that dies between them still leaves a record, and `collapse` reports
  it as `pending` rather than losing it. A read is one `single` event.
- `WriterGrant` — who may commit a write from the channel. A removal stamps
  `removed_at`; re-adding is a new live row.
- `Confirmation` — a prepare/commit token. Only the token's hash is held.
- `AgentActionAudit` — one narrator-agent invocation, written to the existing
  `tcc_ops.agent_action_audit` table. It records that a model was involved and
  what it was given a hash of, never the prompt itself.

There is no update or delete anywhere in these ports except the two state
transitions that are the point of their tables: a grant's `removed_at` and a
confirmation's `consumed_at`.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol

PHASES = ("begin", "end", "single")
CHANNELS = ("teams", "m365-copilot", "cowork", "api-test")
ASSURANCES = ("channel-asserted", "delegated")
ACTION_KINDS = ("read", "write_prepare", "write_commit")
OUTCOMES = ("pending", "ok", "error", "refused", "rejected_by_guard")
GUARD_STATES = ("pass", "rejected", "n/a")
ROLE_WRITER = "writer"

SUMMARY_LIMIT = 2000
ERROR_LIMIT = 2000


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _within(name: str, value: str | None, allowed: Iterable[str]) -> None:
    if value not in tuple(allowed):
        raise ValueError(f"{name} {value!r} is not one of {tuple(allowed)}")


@dataclass(frozen=True)
class ChannelAuditEvent:
    """One row of `tcc_ops.channel_audit`."""

    audit_id: str
    event_seq: int
    phase: str
    correlation_id: str
    channel: str
    user_oid: str
    identity_assurance: str
    tool_name: str
    action_kind: str
    outcome: str
    occurred_at: datetime = field(default_factory=utcnow)
    elapsed_ms: int | None = None
    tenant_id: str | None = None
    user_display_name: str | None = None
    user_upn: str | None = None
    conversation_id: str | None = None
    client_id: int | None = None
    tax_year: int | None = None
    request_summary: str | None = None
    request_sha256: str | None = None
    confirmation_ref: str | None = None
    error: str | None = None
    run_id: str | None = None
    trail_sha256: str | None = None
    numeric_guard: str = "n/a"
    is_deterministic_path: bool = True

    def __post_init__(self) -> None:
        _within("phase", self.phase, PHASES)
        _within("channel", self.channel, CHANNELS)
        _within("identity_assurance", self.identity_assurance, ASSURANCES)
        _within("action_kind", self.action_kind, ACTION_KINDS)
        _within("outcome", self.outcome, OUTCOMES)
        _within("numeric_guard", self.numeric_guard, GUARD_STATES)
        if self.phase == "end" and self.outcome == "pending":
            raise ValueError("an end event cannot be pending")
        if self.phase == "begin" and self.outcome != "pending":
            raise ValueError("a begin event is pending by definition")
        if len(self.request_summary or "") > SUMMARY_LIMIT:
            raise ValueError("request_summary exceeds its column")
        if self.tax_year is not None and not 1900 <= self.tax_year <= 2100:
            raise ValueError(f"tax_year {self.tax_year!r} is not a year")

    def to_dict(self) -> dict:
        row = {name: getattr(self, name) for name in self.__dataclass_fields__}
        row["occurred_at"] = self.occurred_at.isoformat()
        return row


@dataclass(frozen=True)
class ChannelAuditEntry:
    """A request as a reader sees it: its events, collapsed.

    `outcome` is `pending` when there is a `begin` and no `end` — a crash, or a
    request still running. That is reported, not hidden.
    """

    audit_id: str
    outcome: str
    begun_at: datetime
    finished_at: datetime | None
    events: tuple[ChannelAuditEvent, ...]

    @property
    def last(self) -> ChannelAuditEvent:
        return self.events[-1]

    def to_dict(self) -> dict:
        last = self.last
        return {
            "audit_id": self.audit_id, "outcome": self.outcome,
            "begun_at": self.begun_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "tool_name": last.tool_name, "action_kind": last.action_kind,
            "user_oid": last.user_oid, "client_id": last.client_id, "tax_year": last.tax_year,
            "correlation_id": last.correlation_id, "events": len(self.events),
        }


def collapse(events: Iterable[ChannelAuditEvent]) -> list[ChannelAuditEntry]:
    """One entry per `audit_id`, newest first. A `begin` with no `end` is `pending`."""
    grouped: dict[str, list[ChannelAuditEvent]] = {}
    for event in sorted(events, key=lambda e: (e.occurred_at, e.event_seq)):
        grouped.setdefault(event.audit_id, []).append(event)
    entries = []
    for audit_id, group in grouped.items():
        closing = next((e for e in reversed(group) if e.phase in ("end", "single")), None)
        entries.append(ChannelAuditEntry(
            audit_id=audit_id,
            outcome=closing.outcome if closing else "pending",
            begun_at=group[0].occurred_at,
            finished_at=closing.occurred_at if closing else None,
            events=tuple(group),
        ))
    return sorted(entries, key=lambda e: e.begun_at, reverse=True)


@dataclass(frozen=True)
class WriterGrant:
    """A user who may commit writes from the channel."""

    user_oid: str
    added_by: str
    display_name: str | None = None
    role: str = ROLE_WRITER
    added_at: datetime = field(default_factory=utcnow)
    removed_at: datetime | None = None

    def __post_init__(self) -> None:
        _within("role", self.role, (ROLE_WRITER,))
        if not self.user_oid.strip():
            raise ValueError("user_oid is required")

    @property
    def live(self) -> bool:
        return self.removed_at is None

    def removed(self, at: datetime) -> "WriterGrant":
        return replace(self, removed_at=at)


@dataclass(frozen=True)
class Confirmation:
    """A prepare/commit token, by hash. `consumed_at` is set once, atomically."""

    confirmation_id: str
    token_sha256: str
    user_oid: str
    tool_name: str
    args_sha256: str
    expires_at: datetime
    idempotency_key: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    consumed_at: datetime | None = None
    outcome: str | None = None
    result_json: str | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(frozen=True)
class AgentActionAudit:
    """One narrator-agent invocation (`tcc_ops.agent_action_audit`)."""

    action_id: str
    agent_name: str
    occurred_at: datetime = field(default_factory=utcnow)
    run_id: str | None = None
    client_id: int | None = None
    agent_version: str | None = None
    model_deployment: str | None = None
    prompt_hash: str | None = None
    tool_calls: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    user_upn: str | None = None
    is_deterministic_path: bool = False


class ChannelAuditRepository(Protocol):
    """Append-only. Nothing here updates or deletes an event."""

    def append(self, event: ChannelAuditEvent) -> None: ...

    def for_user(
        self, user_oid: str, since: datetime | None = None, until: datetime | None = None,
        tool: str | None = None, limit: int = 200,
    ) -> list[ChannelAuditEvent]:
        """Newest first."""

    def by_correlation(self, correlation_id: str) -> list[ChannelAuditEvent]:
        """Oldest first: every event of one conversation turn, across tools."""


class WriterRepository(Protocol):
    def grant(self, grant: WriterGrant) -> WriterGrant: ...

    def revoke(self, user_oid: str, at: datetime | None = None) -> bool:
        """Stamp `removed_at` on the live row. False if there was none."""

    def is_writer(self, user_oid: str) -> bool: ...

    def live(self) -> list[WriterGrant]: ...


class ConfirmationRepository(Protocol):
    def create(self, confirmation: Confirmation) -> Confirmation: ...

    def find_by_token_hash(self, token_sha256: str) -> Confirmation | None: ...

    def find_by_idempotency_key(self, user_oid: str, key: str) -> Confirmation | None: ...

    def consume(self, confirmation_id: str, at: datetime, idempotency_key: str | None = None) -> bool:
        """Mark consumed if and only if it is not already. True when this call did it."""

    def record_result(self, confirmation_id: str, outcome: str, result_json: str | None) -> None: ...


class AgentActionAuditRepository(Protocol):
    def append(self, action: AgentActionAudit) -> None: ...

    def recent(self, agent_name: str | None = None, limit: int = 100) -> list[AgentActionAudit]: ...
