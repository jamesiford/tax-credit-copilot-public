"""What a run's write path needs to know about the Gold store, without naming it. [ADR-002, ADR-003]

`GoldWriteFailed` is the application's own error: a write or its validation did not hold,
so the run is not usable. The warehouse adapter raises it (an adapter may import the
application's types); the use case catches it and used to import it from the adapter.

`section_9_query_count` is the number of schema-invariant queries the store validates a run
against, and `reap_stranded_runs` closes out runs whose process died. Both are facts about
the store, so the composition root supplies them.
"""
from __future__ import annotations

from application.services import resolve


class GoldWriteFailed(RuntimeError):
    """A write or its validation did not hold. The run is not usable."""


def section_9_query_count() -> int:
    return resolve("section_9_query_count")()


def reap_stranded_runs() -> int:
    return resolve("reap_stranded_runs")()
