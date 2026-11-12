"""Typed failures: a dependency that is missing, unreachable or uninitialised. [03.3, 03.7]

An outage used to arrive as an empty list or an opaque 500, and nothing told a caller
which dependency was down or what to do about it. These carry the three facts a person
needs: *which* dependency, *why*, and *the remedy*. `api` turns one into a 503 that
says so, and a read that can still answer part of a page reports it in a `degraded` list
instead of raising (`DependencyUnavailable.as_degraded`).

Dependency names are a closed convention, not free text: `source_lakehouse`,
`source_sql`, `claims_store`, `operational_store`, and `lookup:<name>` for one lookup table.
"""
from __future__ import annotations

from typing import Any


class DependencyUnavailable(RuntimeError):
    """A named dependency cannot answer. `remedy` is what an operator does next."""

    def __init__(self, dependency: str, reason: str, remedy: str, *, impact: str = "") -> None:
        super().__init__(f"{dependency} unavailable: {reason} {remedy}".strip())
        self.dependency = dependency
        self.reason = reason
        self.remedy = remedy
        self.impact = impact

    def as_degraded(self, impact: str | None = None) -> dict[str, Any]:
        """The entry a response carries in its `degraded` list."""
        return {
            "dependency": self.dependency,
            "impact": impact or self.impact or self.reason,
            "remedy": self.remedy,
        }

    def as_detail(self) -> dict[str, Any]:
        return {"detail": str(self), "dependency": self.dependency, "reason": self.reason, "remedy": self.remedy}


class SourceNotConfigured(DependencyUnavailable):
    """`DATA_SOURCE` resolves to the lakehouse but no lakehouse is named."""

    def __init__(self, missing: tuple[str, ...] = ("FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE")) -> None:
        names = " and ".join(missing)
        super().__init__(
            "source_lakehouse",
            f"the data source is the lakehouse but {names} {'is' if len(missing) == 1 else 'are'} not set.",
            f"Set {names} (and ONELAKE_ENDPOINT for a private-link workspace). "
            "Set DATA_SOURCE=csv only for the local test fixture.",
            impact="no client or payroll data can be read",
        )
        self.missing = missing
