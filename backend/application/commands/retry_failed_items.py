"""Put a batch's failed items back in the queue, with their attempts reset. [ADR-012]

Only `failed` items move; succeeded, skipped and cancelled ones stay as they are, so retrying never repeats work
that finished. A batch that was cancelled is reopened by a retry: the person asking has decided to run it again.
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
class RetryFailedItemsCommand(Command):
    """Re-queue the failed items of one batch."""
    batch_id: str = ""
    policy = Policy.WRITER


def handle_retry_failed_items(command: RetryFailedItemsCommand) -> dict[str, Any]:
    from application.services import get_run_batch_repository

    repo = get_run_batch_repository()
    if repo.get(command.batch_id) is None:
        raise UnknownBatch(command.batch_id)
    requeued = repo.retry_failed(command.batch_id, datetime.now(timezone.utc))
    return {**batch_view(repo.get(command.batch_id)), "requeued": requeued}
