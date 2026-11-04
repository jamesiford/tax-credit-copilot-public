"""What a run's write path needs to know about the Gold store, without naming it. [ADR-002, ADR-003]

`GoldWriteFailed` is the application's own error: a write or its validation did not hold,
so the run is not usable. The warehouse adapter raises it (an adapter may import the
application's types); the use case catches it and used to import it from the adapter.

`section_9_query_count` is the number of schema-invariant queries the store validates a run
against, and `reap_stranded_runs` closes out runs whose process died. Both are facts about
the store, so the composition root supplies them.
"""
from __future__ import annotations

from typing import Any

from application.services import resolve


class GoldWriteFailed(RuntimeError):
    """A write or its validation did not hold. The run is not usable."""


def section_9_query_count() -> int:
    return resolve("section_9_query_count")()


def reap_stranded_runs() -> int:
    return resolve("reap_stranded_runs")()


def run_envelope(run: dict[str, Any] | None, in_flight: dict[str, Any] | None, *, has_rows: bool = True) -> dict[str, Any]:
    """The provenance block every Gold-read screen shows above its figures (produced_at, in_flight)."""
    return resolve("gold_run_envelope")(run, in_flight, has_rows=has_rows)


def employee_filters() -> dict[str, Any]:
    """The whitelist of columns the employee grid may filter on, with their types."""
    return resolve("gold_employee_filters")


def near_filters() -> dict[str, Any]:
    """The same whitelist for the near-threshold cohort, which aliases its columns differently."""
    return resolve("gold_near_filters")
