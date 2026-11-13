"""Start a program draft from the scaffold template. [F05.3]

A **command** (policy: writer): it creates a proposal, never a program. Every statutory value in the template is `null` and
flagged, so the draft fails validation until a person fills it in from a cited source. [ADR-005]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class CreateProgramDraftCommand(Command):
    """Propose a new program: its code, name and state, and optionally the tax years to scaffold."""
    code: str = ""
    name: str = ""
    state: str = ""
    years: tuple[int, ...] = ()
    policy = Policy.WRITER


def handle_create_program_draft(command: CreateProgramDraftCommand) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    draft = lifecycle.create(get_program_draft_repository(), code=command.code, name=command.name, state=command.state,
                             years=list(command.years), actor=command.actor)
    return draft_view(draft)
