"""Validate a program draft's documents. [F05.3]

A **command** (policy: writer) because the result is stored and moves the draft's status (errors: `needs_changes`). It returns
every finding, field-addressed, with errors first. A pass means well-formed, never verified. [ADR-005]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class ValidateProgramDraftCommand(Command):
    """Validate the draft's stored documents."""
    draft_id: str = ""
    policy = Policy.WRITER


def handle_validate_program_draft(command: ValidateProgramDraftCommand) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    draft, result = lifecycle.validate(get_program_draft_repository(), command.draft_id, command.actor)
    return {**draft_view(draft), "validation": result}
