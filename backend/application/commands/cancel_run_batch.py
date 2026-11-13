"""Stop a batch: queued items are cancelled, an item already running finishes. [ADR-012]

Cooperative on purpose. A run that is mid-write is never abandoned, because a half-written Gold run is the state
the stranded-run reaper exists to clean up. Cancelling an already finished batch changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from application.identity import Policy
from application.mediator import Command
from application.runs.errors import UnknownBatch
from application.runs.views import batch_view


@dataclass(frozen=True)
class CancelRunBatchCommand(Command):
    """Cancel one batch by id."""
    batch_id: str = ""
    policy = Policy.WRITER


def handle_cancel_run_batch(command: CancelRunBatchCommand) -> dict[str, Any]:
    from application.services import get_run_batch_repository

    repo = get_run_batch_repository()
    if repo.get(command.batch_id) is None:
        raise UnknownBatch(command.batch_id)
    cancelled = repo.cancel(command.batch_id, datetime.now(timezone.utc))
    return {**batch_view(repo.get(command.batch_id)), "cancelled_now": cancelled}
