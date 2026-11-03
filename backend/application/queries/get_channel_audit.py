"""The channel audit trail for one user, newest first. [CH-03]

A query: it reads the durable trail and changes nothing. Events come back newest
first, and `entries` collapses them to one row per request so a `begin` with no
`end` shows as `pending` — the signature of a crash or a request still running.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from application.mediator import Query
from domain.channel import collapse

MAX_LIMIT = 500


@dataclass(frozen=True)
class GetChannelAuditQuery(Query):
    user_oid: str = ""
    since: datetime | None = None
    until: datetime | None = None
    tool: str | None = None
    limit: int = 200

    def __post_init__(self) -> None:
        if not self.user_oid.strip():
            raise ValueError("user_oid is required")
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")


def handle_get_channel_audit(query: GetChannelAuditQuery) -> dict[str, Any]:
    from application.wiring import get_channel_audit_repository

    events = get_channel_audit_repository().for_user(
        query.user_oid, since=query.since, until=query.until, tool=query.tool, limit=query.limit,
    )
    return {
        "user_oid": query.user_oid,
        "events": [e.to_dict() for e in events],
        "entries": [e.to_dict() for e in collapse(events)],
        "limit": query.limit,
    }
