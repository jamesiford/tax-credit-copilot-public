"""What the numeric guard returns. [ADR-008]

A `Numeral` is one figure found in text; a `Violation` is one the guard refused and
why; a `GuardResult` is the verdict. Split out of `numeric_guard` (which re-exports
them, so every import path is unchanged) so the guard reads as the rule and not as
the bookkeeping. Standard library only: vendored with the guard into the
orchestrator container.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

PASS = "pass"
REJECTED = "rejected"


@dataclass(frozen=True)
class Numeral:
    """One figure found in a piece of text."""

    text: str
    start: int
    end: int
    kind: str  # number | money | percent | abbreviated | ordinal | year | date | structural | non_ascii
    value: Decimal | None = None
    percent: bool = False
    abbreviated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """The JSON-safe form: the value as a plain decimal string, never a float."""
        return {
            "text": self.text, "start": self.start, "end": self.end, "kind": self.kind,
            "value": None if self.value is None else format(self.value, "f"),
        }


@dataclass(frozen=True)
class Violation:
    """A numeral the guard refused, and why."""

    numeral: Numeral
    reason: str
    stage: str = "final"
    nearest: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        """The JSON-safe form, including the nearest fact (what a changed digit probably meant)."""
        return {
            "numeral": self.numeral.to_dict(), "reason": self.reason, "stage": self.stage,
            "nearest_fact": None if self.nearest is None else format(self.nearest, "f"),
        }


@dataclass(frozen=True)
class GuardResult:
    """The verdict on one text: `pass`, or `rejected` with every violation."""

    status: str
    violations: tuple[Violation, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == PASS

    def to_dict(self) -> dict[str, Any]:
        """The JSON-safe form."""
        return {"status": self.status, "violations": [v.to_dict() for v in self.violations]}
