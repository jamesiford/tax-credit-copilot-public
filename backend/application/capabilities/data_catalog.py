"""`data_catalog` — what can be asked of the data, and nothing from the data. [CH-16d]

The model's only way to learn a column's name, meaning, unit and allowed aggregations, so the
description it reads is the semantic model's own and never a guess. No row is read and no value
appears: the catalog is the model, filtered to what THIS caller can use right now.

Filtered, honestly: a dataset whose source is switched off or not configured here is left out and
the result says how many were, rather than listing something that would fail. A blocked column is
never listed. Over Copilot Cowork, for a caller who is not a writer, the result also says that
raw employee-level values are unavailable there, so the model does not plan a query that will be
refused.

Compact by construction: with no arguments, one line per dataset; `dataset` gives that dataset's
columns; `search` narrows both by a word in a name or description.
"""
from __future__ import annotations

from typing import Any

from application.capabilities import _support as s
from application.capabilities.data_access import is_cowork, service
from application.capabilities.envelope import Provenance, ToolResult
from application.data.semantic_model import Column, Dataset, Sensitivity
from application.identity import Principal

MAX_COLUMNS_PER_SEARCH = 15
_COWORK_NOTE = (
    "Over Copilot Cowork, rows that list individual employees are not available unless the user is "
    "entitled to make changes; counts, sums and averages over employees are."
)
_NEXT_STEP = "Pass dataset=<name> to see a dataset's columns, then call data_query with those names exactly."
_SMALL_GROUPS_NOTE = (
    "An aggregate over employee-level data leaves out any group of fewer than {k} people and says how many it left "
    "out; that is the platform's privacy rule, so do not try to get around it with a finer grouping or a narrower filter."
)
_NO_MATCH = (
    "No dataset or column matches that search, so the data has nothing for it. Say so; do not guess a "
    "column name. Try a different word, or call with no search to list every dataset."
)


def _column(column: Column) -> dict[str, Any]:
    return {
        "name": column.logical, "type": column.type.value, "role": column.role.value,
        "sensitivity": column.sensitivity.value, "unit": column.unit, "description": column.description,
        "aggregations": sorted(a.value for a in column.aggregations),
        "operators": sorted(o.value for o in column.operators),
        **({"values": list(column.choices)} if column.choices else {}),
    }


def _overview(dataset: Dataset) -> dict[str, Any]:
    return {
        "name": dataset.name, "source": dataset.source.value, "grain": dataset.grain, "description": dataset.description,
        "employee_level": dataset.employee_level, "method_dependent": dataset.method_column is not None,
        "tax_year_column": dataset.year_column,
        "column_count": sum(1 for c in dataset.columns if c.queryable),
    }


def _matches(text: str, needle: str) -> bool:
    return needle in text.lower()


def _usable(dataset: Dataset, needle: str | None) -> list[Column]:
    columns = [c for c in dataset.columns if c.queryable]
    if needle:
        columns = [c for c in columns if _matches(f"{c.logical} {c.description}", needle)]
    return columns


def _entry(dataset: Dataset, *, detail: bool, needle: str | None) -> dict[str, Any] | None:
    entry = _overview(dataset)
    if detail:
        entry["columns"] = [_column(c) for c in _usable(dataset, needle)]
        entry["engine_notes"] = [{"about": a, "note": n} for a, n in dataset.engine_notes]
        entry["joins"] = [j.name for j in dataset.joins]
        return entry
    if needle:
        own = _matches(f"{dataset.name} {dataset.grain} {dataset.description}", needle)
        found = _usable(dataset, needle)[:MAX_COLUMNS_PER_SEARCH]
        if not own and not found:
            return None
        entry["columns"] = [_column(c) for c in found]
    return entry


def _notes(principal: Principal, dataset: str | None, omitted: int, *, missed: bool = False) -> list[str]:
    notes = [_NEXT_STEP] if dataset is None else []
    if missed:
        notes.append(_NO_MATCH)
    if omitted:
        notes.append(f"{omitted} dataset(s) are not available in this environment and are not listed.")
    if is_cowork(principal):
        notes.append(_COWORK_NOTE)
    return notes


def _entries(dataset: str | None, needle: str | None) -> tuple[list[dict[str, Any]], int]:
    """The catalog entries this environment can serve for the request, and how many datasets it cannot."""
    svc = service()
    sources = svc.available_sources()
    asked = [d for d in svc.model.datasets if dataset is None or d.name == dataset]
    entries = [e for d in asked if d.source in sources if (e := _entry(d, detail=dataset is not None, needle=needle))]
    return entries, sum(1 for d in asked if d.source not in sources)


def _facts(principal: Principal, dataset: str | None, search: str | None) -> dict[str, Any]:
    needle = search.strip().lower() if search else None
    entries, omitted = _entries(dataset, needle)
    missed = bool(needle) and not entries and not omitted
    notes = _notes(principal, dataset, omitted, missed=missed)
    if any(e["employee_level"] for e in entries):
        notes.append(_SMALL_GROUPS_NOTE.format(k=service().min_group_size))
    return {"dataset_count": len(entries), "datasets": entries, "notes": notes}


def _column_row(c: dict[str, Any]) -> tuple[str, ...]:
    person = c["sensitivity"] == Sensitivity.EMPLOYEE_LEVEL.value
    return (
        c["name"], f"{c['role']}, employee level" if person else c["role"], c["unit"] or s.ABSENT, c["description"],
        ", ".join(c["aggregations"]) or s.ABSENT, ", ".join(c["operators"]) or s.ABSENT,
    )


def _detail_blocks(entry: dict[str, Any]) -> list:
    return [
        s.heading(f"{entry['name']} · {entry['grain']}"),
        s.table(("Column", "Role", "Unit", "Meaning", "Aggregations", "Filters"), [_column_row(c) for c in entry["columns"]]),
    ]


def _blocks(facts: dict[str, Any]) -> list:
    blocks = [s.heading("Queryable data")]
    detailed = [e for e in facts["datasets"] if "columns" in e]
    for entry in detailed:
        blocks.extend(_detail_blocks(entry))
    if not detailed:
        blocks.append(s.table(("Dataset", "One row is", "Source"), [(e["name"], e["grain"], e["source"]) for e in facts["datasets"]]))
    blocks.extend(s.callout(note) for note in facts["notes"])
    return blocks


def data_catalog(principal: Principal, dataset: str | None = None, search: str | None = None) -> ToolResult:
    """The semantic model for this caller, optionally narrowed to one dataset and/or a search word."""
    facts = _facts(principal, dataset, search)
    return s.result(
        "data_catalog", facts, _blocks(facts),
        provenance=Provenance(source="semantic model; holds no values from the data"),
    )
