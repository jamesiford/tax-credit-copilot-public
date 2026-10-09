"""Human decisions about what an agent found.

Commands. A finding is a machine observation; a *resolution* is a person
accepting responsibility for it, and that is a change to what the business
believes. Every one carries who decided and when, and the store is append-only:
changing your mind closes the prior decision rather than erasing it, because
somebody decided something once and that fact should survive.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from application.mediator import Command


class InvalidResolution(ValueError):
    """The decision is not self-consistent.

    A `ValueError` subclass so a router can map it to 422 without knowing what
    made it invalid, and so a non-HTTP caller sees an ordinary Python error.
    """


@dataclass(frozen=True)
class ResolveFindingCommand(Command):
    """Record a decision about one finding.

    `keep_worksite` is required when the resolution is `assign`: assigning an
    employee to a unit without naming the unit records a decision nobody can
    act on, and the whole point is that the next run applies it.
    """

    finding_id: str = ""
    client_id: int = 0
    tax_year: int = 0
    resolution: str = ""
    keep_worksite: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise InvalidResolution("finding_id is required")
        if self.resolution == "assign" and not self.keep_worksite:
            raise InvalidResolution(
                "assign needs keep_worksite — which unit the employee is counted at."
            )


@dataclass(frozen=True)
class ReopenFindingCommand(Command):
    """Withdraw a decision, leaving the finding open again."""

    finding_id: str = ""
    client_id: int = 0

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise InvalidResolution("finding_id is required")


def handle_resolve_finding(command: ResolveFindingCommand) -> dict[str, Any]:
    from application.wiring import get_finding_repository as get_repository
    from infrastructure.persistence.sqlite_findings import FindingResolution

    entry = FindingResolution(
        finding_id=command.finding_id,
        client_id=command.client_id,
        tax_year=command.tax_year,
        resolution=command.resolution,
        detail={"keep_worksite": command.keep_worksite} if command.keep_worksite else None,
        note=command.note,
        decided_by=command.actor,
        decided_at=datetime.now(timezone.utc).isoformat(),
    )
    return get_repository().record(entry).to_dict()


def handle_reopen_finding(command: ReopenFindingCommand) -> dict[str, Any]:
    from application.wiring import get_finding_repository as get_repository

    get_repository().reopen(
        finding_id=command.finding_id,
        client_id=command.client_id,
        decided_by=command.actor,
    )
    return {
        "finding_id": command.finding_id,
        "resolution": None,
        "requires_decision": True,
    }
