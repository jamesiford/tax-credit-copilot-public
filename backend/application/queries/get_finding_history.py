"""Every decision ever recorded against one finding.

A decision is closed rather than deleted when somebody changes their mind, so the history
is the audit trail of who decided what and when.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query


@dataclass(frozen=True)
class GetFindingHistoryQuery(Query):
    """The decisions recorded against one finding of one client."""

    client_id: int
    finding_id: str


def handle_get_finding_history(query: GetFindingHistoryQuery) -> dict[str, Any]:
    from application.services import get_finding_repository

    return {
        "finding_id": query.finding_id,
        "history": [r.to_dict() for r in get_finding_repository().history(query.client_id, query.finding_id)],
    }
