"""Submit a program draft for review. [F05.3]

A **command** (policy: writer). Only a draft whose CURRENT documents validated with no errors can be submitted, so a reviewer
never opens something that was already known to be broken.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class RequestProgramReviewCommand(Command):
    """Ask for review of the draft as it stands."""
    draft_id: str = ""
    policy = Policy.WRITER


def handle_request_program_review(command: RequestProgramReviewCommand) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    return draft_view(lifecycle.request_review(get_program_draft_repository(), command.draft_id, command.actor))
