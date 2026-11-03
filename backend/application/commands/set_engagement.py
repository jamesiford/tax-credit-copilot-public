"""Declare whether a programme is our mandate for a client. [CH-05]

A **command**: engagement decides which cells count as our responsibility, so who
set it, and when, is recorded on the row (`set_by`, `set_at`). The previous
engagement is closed, not overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from application.identity import Policy
from application.mediator import Command
from domain.claims import EngagementScope, ProgramEngagement


@dataclass(frozen=True)
class SetEngagementCommand(Command):
    client_id: int = 0
    program_code: str = ""
    scope: EngagementScope = EngagementScope.PROSPECTIVE
    note: str | None = None
    policy = Policy.WRITER


def build_engagement(command: SetEngagementCommand, at: datetime | None = None) -> ProgramEngagement:
    return ProgramEngagement(
        client_id=command.client_id,
        program_code=command.program_code,
        scope=command.scope,
        note=command.note,
        set_by=command.actor,
        set_at=at or datetime.now(timezone.utc),
    )


def handle_set_engagement(command: SetEngagementCommand) -> dict[str, Any]:
    from application.wiring import get_claim_repository

    return get_claim_repository().set_engagement(build_engagement(command)).to_dict()
