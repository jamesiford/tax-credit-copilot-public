"""A deterministic stand-in for the knowledge source, for tests and local runs. [RM-15, ADR-010]

It holds a small in-memory corpus and ranks passages by how many words they share with the query,
so the same question always returns the same passages in the same order. It is the only
implementation besides "none" today; Foundry IQ is designed (docs/architecture/KNOWLEDGE-AND-IQ.md),
not built.

The built-in corpus is SYNTHETIC. It says so in its own text and its citations are `synthetic:`
identifiers, and it contains made-up figures on purpose: they are what the tests use to show that
a number read in a passage never reaches a reply. It is not statute and must never be edited to look
like it (the repository invents no statute).

Standard library only; vendored into the orchestrator.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from application.knowledge import Passage

_WORDS = re.compile(r"[a-z]{3,}")
RETRIEVED = datetime(2026, 1, 1, tzinfo=timezone.utc)

SYNTHETIC_CORPUS: tuple[Passage, ...] = (
    Passage(
        "Synthetic example, not statute. A hypothetical program pays a credit of $1,234 per net-new qualifying job "
        "when the employer holds a designation for the location.",
        "Synthetic corpus", "synthetic:example-credit", RETRIEVED,
    ),
    Passage(
        "Synthetic example, not statute. A hypothetical eligibility rule counts an employee who works at least 99 hours "
        "a week, and a hypothetical base year is the first complete year of payroll.",
        "Synthetic corpus", "synthetic:example-eligibility", RETRIEVED,
    ),
    Passage(
        "Synthetic example, not statute. A hypothetical definition: a location is a worksite with its own address "
        "and its own pay periods.",
        "Synthetic corpus", "synthetic:example-definition", RETRIEVED,
    ),
)


def _words(text: str) -> set[str]:
    return set(_WORDS.findall(text.lower()))


class FakeKnowledge:
    """Keyword-overlap retrieval over a fixed corpus."""

    def __init__(self, corpus: Iterable[Passage] | None = None) -> None:
        self._corpus: Sequence[Passage] = tuple(SYNTHETIC_CORPUS if corpus is None else corpus)
        self.queries: list[str] = []

    def search(self, query: str, *, top: int) -> list[Passage]:
        """The passages sharing the most words with `query` (at least one), best first, then in corpus order."""
        self.queries.append(query)
        asked = _words(query)
        scored = [(len(asked & _words(p.text)), n, p) for n, p in enumerate(self._corpus)]
        return [p for score, _, p in sorted(scored, key=lambda s: (-s[0], s[1]))[:max(0, top)] if score > 0]
