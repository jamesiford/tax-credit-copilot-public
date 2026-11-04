"""A human's answer to something an agent found. [ADR-003]

The record is a domain fact, so the use case that creates it and every store that keeps it
share this one definition instead of the use case importing it from a SQLite adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FindingResolution:
    """A human's answer to something an agent found."""

    finding_id: str
    client_id: int
    tax_year: int
    resolution: str          # accept | assign | drop | flag
    decided_by: str
    decided_at: str
    detail: dict[str, Any] | None = None   # e.g. which worksite to keep
    note: str | None = None
    superseded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "client_id": self.client_id,
            "tax_year": self.tax_year,
            "resolution": self.resolution,
            "detail": self.detail,
            "note": self.note,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "superseded_at": self.superseded_at,
        }

