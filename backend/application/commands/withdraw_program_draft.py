"""Withdraw a program draft that will not go ahead. [F05.3]

A **command** (policy: writer). The draft and its audit trail stay readable; only an exported draft cannot be withdrawn, because
its files may already be committed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class WithdrawProgramDraftCommand(Command):
    """Close the draft, with an optional reason."""
    draft_id: str = ""
    reason: str | None = None
    policy = Policy.WRITER


def handle_withdraw_program_draft(command: WithdrawProgramDraftCommand) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    return draft_view(lifecycle.withdraw(get_program_draft_repository(), command.draft_id, command.actor, command.reason))
