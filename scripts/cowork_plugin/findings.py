"""What a validator reports. [CH-10]

Codes follow the platform's own where one exists (`ASKILL-P001` ...), and use `TCC-` for
the checks this repository adds on top: tool references, customer neutrality, size.
"""
from __future__ import annotations

from dataclasses import dataclass

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Finding:
    """One problem, where it is, and how to read it."""

    code: str
    path: str
    message: str
    severity: str = ERROR

    def __str__(self) -> str:
        return f"{self.severity.upper():<7} {self.code:<13} {self.path}: {self.message}"


def errors(findings: list[Finding]) -> list[Finding]:
    """Only the findings that stop a package being built."""
    return [f for f in findings if f.severity == ERROR]
