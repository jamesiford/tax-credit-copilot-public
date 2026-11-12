"""Match a mapping's columns to the columns a lake table actually carries. [06.3]

The customer's DDL spells a tenant column `Accountid`; a Delta filter is case-sensitive. So the actual
spelling is resolved from the table's own schema at first read, and the same resolution drives the
validation report, so what the reader tolerates and what the report says are one rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import SourceMapping, TableMap


@dataclass(frozen=True)
class ColumnResolution:
    """How one table's mapped fields line up with its actual columns."""

    table: str
    found: dict[str, str] = field(default_factory=dict)  # logical field -> actual column
    case_differs: dict[str, tuple[str, str]] = field(default_factory=dict)  # field -> (mapped, actual)
    missing_required: tuple[str, ...] = ()
    missing_optional: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()  # lake columns the mapping does not use

    @property
    def ok(self) -> bool:
        return not self.missing_required


def resolve_columns(table: TableMap, actual: list[str], case_insensitive: bool = True) -> ColumnResolution:
    """Resolve each mapped field to an actual column: exact first, then (if allowed) ignoring case."""
    by_lower: dict[str, str] = {}
    for name in actual:
        by_lower.setdefault(name.lower(), name)
    exact = set(actual)
    found: dict[str, str] = {}
    case_differs: dict[str, tuple[str, str]] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    for name, mapped in table.fields.items():
        if mapped.column in exact:
            found[name] = mapped.column
        elif case_insensitive and mapped.column.lower() in by_lower:
            found[name] = by_lower[mapped.column.lower()]
            case_differs[name] = (mapped.column, found[name])
        else:
            (missing_required if mapped.required else missing_optional).append(name)
    used = set(found.values())
    return ColumnResolution(
        table.logical, found, case_differs, tuple(missing_required), tuple(missing_optional),
        tuple(sorted(c for c in actual if c not in used)),
    )


def resolve_for(mapping: SourceMapping, logical: str, actual: list[str]) -> ColumnResolution:
    return resolve_columns(mapping.table(logical), actual, mapping.case_insensitive)
