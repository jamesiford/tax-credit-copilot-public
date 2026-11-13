"""Replace a program draft's documents, naming the version the editor read. [F05.3]

A **command** (policy: writer). A full replace with optimistic concurrency: two editors cannot silently overwrite each other,
and a draft under review cannot be edited, because the review is of the documents it holds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class EditProgramDraftCommand(Command):
    """The new base pack and year packs, the version they were read at, and optionally a new name."""
    draft_id: str = ""
    expected_version: int = 0
    pack: dict[str, Any] | None = None
    years: dict[str, dict[str, Any]] = field(default_factory=dict)
    name: str | None = None
    policy = Policy.WRITER


def handle_edit_program_draft(command: EditProgramDraftCommand) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    draft = lifecycle.edit(get_program_draft_repository(), command.draft_id, command.expected_version, (command.pack, command.years),
                           actor=command.actor, name=command.name)
    return draft_view(draft)
