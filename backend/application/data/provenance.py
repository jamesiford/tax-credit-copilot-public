"""Provenance: what a data result is, where it came from and what bounded it. [CH-16c]

Every result carries enough to be audited and to be stated honestly in the answer: the dataset
and physical table, the question as it was asked, a hash of the statement that ran, the rows
returned and whether the cap cut the list, the run behind the data, and when it was current.

Two rules shape it:

- **The statement hash covers structure, never values.** It is a SHA-256 of the statement text
  (which carries a tenant marker, not a client id, and no values) and, separately, of the
  parameters' *types and count*. Two people asking the same question about different clients
  share a hash, which is the point: it identifies the query shape, not the data asked about.
- **A filter value is shown only where it is not sensitive.** A value filtered on an
  employee-level or identifying column appears as `<redacted>`; the column and operator always do.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from application.data.build import BuiltQuery
from application.data.dialect import SchemaNames
from application.data.executor import Rows
from application.data.plan import FilterPlan
from application.data.semantic_model import Currency, Sensitivity

REDACTED = "<redacted>"


@dataclass(frozen=True, slots=True)
class LiveRun:
    """The calculation run behind a live-run dataset: which assumptions and statute produced the rows."""

    run_id: str
    rule_pack_version: str | None
    step1_assumption_set_id: str | None
    onezero_assumption_set_id: str | None
    completed_at: str | None


@dataclass(frozen=True, slots=True)
class QueryProvenance:
    """The audit and narration record of one data result."""

    dataset: str
    source: str
    physical_table: str
    source_line: str
    client_id: int
    tax_years: tuple[int, ...]
    method: str | None
    method_dependent: bool
    select: tuple[str, ...]
    group_by: tuple[str, ...]
    measures: tuple[dict[str, str], ...]
    filters: tuple[dict[str, Any], ...]
    statement_sha256: str
    params_sha256: str
    param_count: int
    row_count: int
    row_limit: int
    truncated: bool
    currency: str
    run: LiveRun | None
    as_of: str
    as_of_basis: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe form for the audit trail and the envelope."""
        data = {name: getattr(self, name) for name in self.__slots__}
        data["run"] = None if self.run is None else {k: getattr(self.run, k) for k in self.run.__slots__}
        for key in ("tax_years", "select", "group_by", "measures", "filters", "notes"):
            data[key] = list(data[key])
        return data


def build_provenance(built: BuiltQuery, schemas: SchemaNames, rows: Rows, *,
                     row_limit: int, run: LiveRun | None, executed_at: datetime) -> QueryProvenance:
    """The provenance for a result, from the statement that ran and the rows it returned."""
    plan, dataset = built.plan, built.plan.dataset
    table = f"{schemas.name(dataset.schema)}.{dataset.table}"
    as_of, basis = (run.completed_at, "run_completed_at") if run and run.completed_at else (
        executed_at.isoformat(timespec="seconds"), "query_time")
    return QueryProvenance(
        dataset=dataset.name, source=dataset.source.value, physical_table=table,
        source_line=f"Source: {dataset.source.value} {table}", client_id=plan.client_id,
        tax_years=plan.tax_years, method=plan.method, method_dependent=dataset.method_column is not None,
        select=tuple(r.ref for r in plan.select), group_by=tuple(r.ref for r in plan.group_by),
        measures=tuple({"column": m.ref.ref if m.ref else "*", "agg": m.agg.value, "as": m.alias} for m in plan.measures),
        filters=tuple(_filter(f) for f in plan.filters),
        statement_sha256=sha256_text(built.sql), params_sha256=sha256_text(json.dumps(param_structure(built.params))),
        param_count=len(built.params), row_count=rows.row_count, row_limit=row_limit, truncated=rows.truncated,
        currency=dataset.currency.value, run=run, as_of=as_of, as_of_basis=basis,
        notes=_notes(built, rows, row_limit, run),
    )


def sha256_text(text: str) -> str:
    """Hex SHA-256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def param_structure(params: list[Any]) -> list[str]:
    """The parameters' types in order: the shape of the binding with no value in it."""
    return [type(p).__name__ for p in params]


def _filter(item: FilterPlan) -> dict[str, Any]:
    shown = item.ref.column.sensitivity is Sensitivity.PUBLIC_AGGREGATE
    return {"column": item.ref.ref, "op": item.op.value, "value": _plain(item.value) if shown else REDACTED}


def _plain(value: Any) -> Any:
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value) if isinstance(value, Decimal) else value


def _notes(built: BuiltQuery, rows: Rows, row_limit: int, run: LiveRun | None) -> tuple[str, ...]:
    plan, notes = built.plan, []
    if rows.truncated:
        notes.append(f"Showing the first {rows.row_count} rows; more rows matched and were not returned.")
    if row_limit < plan.limit:
        notes.append(f"The server's row cap ({row_limit}) is lower than the limit asked for ({plan.limit}).")
    if plan.dataset.method_column is not None:
        notes.append("Method: both Min-Max and Pay Period, each row labelled." if plan.method == "both"
                     else f"Method: {plan.method} only.")
    if plan.dataset.currency is Currency.LIVE_RUN:
        notes.append(f"Rows are from the client's live run {run.run_id}." if run else
                     "Rows are from the client's live run; its identity could not be read.")
    elif plan.dataset.currency is Currency.IS_CURRENT:
        notes.append("Current rows only; superseded rows are excluded.")
    return tuple(notes)
