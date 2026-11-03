"""Who a channel user is, by name: the port and the rule for when to ask. [CH-15a]

Teams tells the gateway WHICH person is talking (an object id) but not what they are
called, so every audit row for a Teams user read "(name not provided)" and a write was
attributed to a GUID. A directory can answer; this module says what is asked of it and
when, and nothing more. The adapter is `infrastructure.auth.graph_people`.

Standard library only: the gateway imports this, and the gateway holds no framework.
A name and a UPN are personal data, so they travel only in the `ActingUser` the audit
columns are built from; nothing here logs them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from application.identity import ActingUser

#: What the orchestrator sends when the channel gave it no name (`channel_orchestrator`
#: `NAME_UNKNOWN`). It is a placeholder, not somebody's name, so it triggers a lookup.
PLACEHOLDER_NAME = "(name not provided)"


@dataclass(frozen=True)
class ResolvedPerson:
    """What the directory knows about one person; either field may be absent."""

    display_name: str | None
    upn: str | None


class DisplayNameResolver(Protocol):
    """Look a person up by object id. Fail-soft: `None` for ANY failure, never an exception."""

    def resolve(self, oid: str) -> ResolvedPerson | None: ...


def needs_resolution(acting: ActingUser) -> bool:
    """Whether the acting user has no usable name yet (missing, blank or the placeholder)."""
    name = (acting.display_name or "").strip()
    return not name or name.lower() == PLACEHOLDER_NAME
