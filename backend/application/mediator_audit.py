"""The in-memory record of attempted writes. [CH-04, AI-08]

Split out of `mediator.py` so the pipeline reads as a pipeline; `application.mediator`
re-exports these names, so every existing import keeps working.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque

#: What `actor` falls back to. An audit record says so rather than presenting a
#: default as a person, because "system" in an actor column looks like a
#: service account somebody could go and ask about.
UNATTRIBUTED = "system"


@dataclass(frozen=True)
class AuditRecord:
    """One attempted write, recorded whether or not it succeeded.

    A failed write is the more interesting half: "somebody tried to resolve this
    finding and it errored" is a question that gets asked, and a trail that only
    holds successes cannot answer it.
    """

    request: str
    actor: str
    attributed: bool
    at: str
    elapsed_ms: float
    outcome: str
    error: str | None = None


class AuditLog:
    """A bounded in-memory trail: a support aid, not the destination. It dies with
    the process; the durable trails are `tcc_ops.agent_action_audit`,
    `tcc_ops.channel_audit` and the per-run manifest.
    """

    def __init__(self, limit: int = 2000) -> None:
        self._records: Deque[AuditRecord] = deque(maxlen=limit)

    def record(self, entry: AuditRecord) -> None:
        self._records.append(entry)

    @property
    def records(self) -> list[AuditRecord]:
        return list(self._records)
