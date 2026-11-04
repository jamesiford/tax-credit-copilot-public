"""[L2] CALC-08 — designation timelines and parallel-calc flags for a state.

Surfaces which locations changed designation between the base year and the analysis
year, a change that, combined with net-new jobs, spawns two concurrent calculations for
the same location.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query


@dataclass(frozen=True)
class GetDesignationSplitsQuery(Query):
    """Designation timelines for `state` in `tax_year`."""

    state: str
    tax_year: int = 2025


def handle_get_designation_splits(query: GetDesignationSplitsQuery) -> dict[str, Any]:
    """The designation timelines and parallel-calc flags for the state."""
    from tools.designation import detect_designation_splits

    return detect_designation_splits(query.state, query.tax_year)
