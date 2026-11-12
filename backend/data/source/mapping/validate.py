"""Compare a source mapping with the lake it describes, and say precisely what differs. [06.4]

The report separates what stops the engine from what only deserves a look:

* **errors**   a required table, or a required field's column, is absent; a required column's type cannot be
               read as the mapped type. The engine cannot read the source faithfully.
* **warnings** an optional table or field is absent (it reads as empty), a column's case differs from the
               mapping (the reader matches it case-insensitively), a column is stored as another type but is read
               with coercion, or the lake carries columns the mapping does not use.

The same column resolution (`columns.resolve_columns`) drives the reader, so what the reader tolerates and what
this report says are one rule. No data is read: only each table's schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .columns import ColumnResolution, resolve_for
from .model import SourceMapping

#: Delta type names that read as each mapped Arrow type with no coercion.
_NATIVE = {
    "int64": {"long", "integer", "short", "byte"}, "int32": {"integer", "short", "byte"}, "string": {"string"}, "bool": {"boolean"},
    "double": {"double", "float"}, "date32": {"date"}, "timestamp[us]": {"timestamp", "timestamp_ntz"},
}
#: Types a mapped decimal or number is still read from, by coercion.
_COERCIBLE = {"decimal128(18, 2)": {"string", "double", "float", "long", "integer"}}


@dataclass(frozen=True)
class TableReport:
    logical: str
    physical: str
    optional: bool
    present: bool
    resolution: ColumnResolution | None = None
    retyped: dict[str, tuple[str, str]] = field(default_factory=dict)  # field -> (mapped, actual)
    incompatible: tuple[str, ...] = ()

    @property
    def errors(self) -> list[str]:
        if not self.present:
            return [] if self.optional else [f"{self.logical}: table {self.physical} is absent"]
        out = [f"{self.logical}: no column for required field {f}" for f in (self.resolution.missing_required if self.resolution else ())]
        return out + [f"{self.logical}.{f}: stored as {self.retyped[f][1]}, cannot be read as {self.retyped[f][0]}" for f in self.incompatible]

    @property
    def warnings(self) -> list[str]:
        if not self.present:
            return [f"{self.logical}: optional table {self.physical} is absent; it reads as empty"] if self.optional else []
        r, out = self.resolution, []
        assert r is not None
        out += [f"{self.logical}: no column for optional field {f}; it reads as empty" for f in r.missing_optional]
        out += [f"{self.logical}.{f}: column is spelled {a!r}, mapped as {m!r}; matched ignoring case" for f, (m, a) in r.case_differs.items()]
        out += [f"{self.logical}.{f}: stored as {a}, mapped as {m}; read with coercion" for f, (m, a) in self.retyped.items() if f not in self.incompatible]
        out += [f"{self.logical}: lake column {c!r} is not mapped (unused)" for c in r.extra]
        return out


@dataclass(frozen=True)
class Report:
    tables: tuple[TableReport, ...]

    @property
    def errors(self) -> list[str]:
        return [m for t in self.tables for m in t.errors]

    @property
    def warnings(self) -> list[str]:
        return [m for t in self.tables for m in t.warnings]

    @property
    def status(self) -> str:
        return "error" if self.errors else "warning" if self.warnings else "ok"

    def summary(self) -> dict:
        return {"status": self.status, "errors": self.errors, "warnings": self.warnings}


def _base_type(actual: str) -> str:
    return "decimal" if actual.lower().startswith("decimal") else actual.lower()


def _retyped(mapping: SourceMapping, logical: str, resolution: ColumnResolution, actual: Mapping[str, str]) -> tuple[dict, tuple]:
    table = mapping.table(logical)
    retyped: dict[str, tuple[str, str]] = {}
    incompatible: list[str] = []
    for name, column in resolution.found.items():
        mapped, stored = table.fields[name].type, _base_type(actual[column])
        if mapped.startswith("decimal") and stored == "decimal" or stored in _NATIVE.get(mapped, ()):
            continue
        retyped[name] = (mapped, actual[column])
        if stored not in _COERCIBLE.get(mapped, ()) and table.fields[name].required:
            incompatible.append(name)
    return retyped, tuple(incompatible)


def validate(mapping: SourceMapping, actual: Mapping[str, Mapping[str, str] | None], physical: Mapping[str, str]) -> Report:
    """`actual`: logical table -> {column: type} (None when the table is absent). `physical`: logical -> physical table name."""
    reports = []
    for logical, table in mapping.tables.items():
        columns = actual.get(logical)
        if columns is None:
            reports.append(TableReport(logical, physical[logical], bool(table.optional_reason), False))
            continue
        resolution = resolve_for(mapping, logical, list(columns))
        retyped, incompatible = _retyped(mapping, logical, resolution, columns)
        reports.append(TableReport(logical, physical[logical], bool(table.optional_reason), True, resolution, retyped, incompatible))
    return Report(tuple(reports))


def render(report: Report) -> str:
    """The report as text a person can act on."""
    lines = [f"source schema: {report.status.upper()}"]
    for title, items in (("ERRORS (the engine cannot read the source faithfully)", report.errors), ("WARNINGS", report.warnings)):
        if items:
            lines += ["", title + ":"] + [f"  - {m}" for m in items]
    return "\n".join(lines)
