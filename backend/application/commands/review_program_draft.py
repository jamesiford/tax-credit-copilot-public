"""Decide a program draft: approve it for export, or send it back with a comment. [F05.3]

A **command** (policy: writer). When `PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER` is on (the default outside local development) the
reviewer must not be anyone who created, edited or submitted the draft. Approval is for EXPORT only: it activates nothing, and it
does not verify any value in the pack. [ADR-005]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class ReviewProgramDraftCommand(Command):
    """`decision` is `approve` or `request_changes`; a request for changes needs a comment."""
    draft_id: str = ""
    decision: str = ""
    comment: str | None = None
    policy = Policy.WRITER


def handle_review_program_draft(command: ReviewProgramDraftCommand) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    draft = lifecycle.review(get_program_draft_repository(), command.draft_id, command.actor, command.decision, command.comment)
    return draft_view(draft)
