"""`data_query` and `data_distinct_values`: governed, read-only questions about one client's data. [CH-16d]

Both are thin on purpose. The specification is validated against the semantic model, the
statement is built from the model's own names with every value bound and the client scope
first, and the service runs it under its limits (`application/data/`). What these functions add
is the capability contract: a typed refusal for every way a question can fail, the Copilot Cowork
rule for employee-level rows, and an envelope the numeric guard can check.

**Client scope is not the model's to choose.** `client_id` is validated by the same entitlement
the API applies to every tool (`api/capabilities.py`), and the orchestrator overwrites whatever
a model passed with the client the conversation resolved. Neither function reads a client from
free text.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from application.capabilities import _support as s
from application.capabilities.data_access import (
    asker, refuse_employee_level_beyond_first_party, refused, service, suppress_small_groups,
)
from application.capabilities.data_render import cell, to_tool_result
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.errors import DataQueryRefused
from application.data.errors import BlockedColumn, QueryError, UnknownColumn, UnknownDataset
from application.data.plan import ResultColumn
from application.data.semantic_model import Role, Sensitivity
from application.data.spec import MAX_LIMIT, MeasureSpec, OrderSpec, QuerySpec
from application.identity import Principal

DEFAULT_DISTINCT = 50
_LISTABLE_ROLES = (Role.DIMENSION, Role.FLAG)
_VALUE = ResultColumn("value", "dimension", "value", None, Sensitivity.PUBLIC_AGGREGATE)


def data_query(principal: Principal, **query: Any) -> ToolResult:
    """Run a structured query. The arguments ARE the specification (`QuerySpec.from_dict` checks the shape)."""
    try:
        spec = QuerySpec.from_dict(query)
        svc = service()
        refuse_employee_level_beyond_first_party(principal, svc.audience_of(spec))
        return to_tool_result(svc.run(spec, principal=asker(principal), suppress_small_groups=suppress_small_groups(principal)))
    except QueryError as exc:
        raise refused(exc) from exc


def _listable(dataset_name: str, column_name: str) -> None:
    """Refuse a column whose values describe people, or that the model does not know. Never lists them."""
    dataset = service().model.dataset(dataset_name)
    if dataset is None:
        raise UnknownDataset("no such dataset; read the catalog for the names", field="dataset")
    column = dataset.column(column_name)
    if column is None:
        raise UnknownColumn("no such column in that dataset; read the catalog for the names", field="column")
    if not column.queryable:
        raise BlockedColumn("that column can never be listed", field="column")
    if column.sensitivity is not Sensitivity.PUBLIC_AGGREGATE or column.role not in _LISTABLE_ROLES:
        raise DataQueryRefused(
            "That column holds values that identify or describe individual people (or is not a category), so its "
            "values are not listed. Ask for a count or an average grouped by a category instead.",
            code="column_not_listable", status=422, extra={"field": "column"},
        )


def _rows_to_fetch(dataset: str, limit: int) -> int:
    """Rows to ask for so that `limit` VALUES come back. A dataset holding both statutory readings returns
    each value once per reading, so asking for `limit` rows listed only half as many values and still said
    the list was cut: a client with 101 worksites could never be enumerated past 50."""
    held = service().model.dataset(dataset)
    return min(limit * 2, MAX_LIMIT) if held is not None and held.method_column else limit


def _values_spec(client_id: int, dataset: str, column: str, tax_years: Any, limit: int) -> QuerySpec:
    years = QuerySpec.from_dict({"dataset": dataset, "client_id": client_id, "tax_years": tax_years}).tax_years
    return QuerySpec(
        dataset=dataset, client_id=client_id, tax_years=years, select=(column,),
        measures=(MeasureSpec("*", "count", "row_count"),), group_by=(column,), order_by=(OrderSpec(column),),
        limit=_rows_to_fetch(dataset, limit),
    )


def _merge(columns: tuple[ResultColumn, ...], rows: tuple[tuple, ...], column: str) -> list[dict[str, Any]]:
    """One entry per value. A dataset holding both statutory readings lists each value once per reading;
    the row counts of those are added, which is a count of rows, not of people."""
    names = [c.label for c in columns]
    totals: Counter = Counter()
    order: list[Any] = []
    for row in rows:
        record = dict(zip(names, row))
        if record[column] not in totals:
            order.append(record[column])
        totals[record[column]] += record["row_count"]
    return [{"value": v, "row_count": totals[v]} for v in order]


def _values_blocks(dataset: str, column: str, values: list[dict[str, Any]], truncated: bool, source: str) -> list:
    blocks = [s.heading(f"Distinct values · {dataset}.{column}")]
    blocks.append(s.table(("Value", "Rows"), [(cell(v["value"], _VALUE), s.cell(v["row_count"], "count")) for v in values])
                  if values else s.paragraph("No values: the client holds no rows for that selection."))
    if truncated:
        blocks.append(s.callout("The list was cut at the limit; there are more values. Filter, or raise the limit up to 100."))
    blocks.append(s.paragraph(f"{source}."))
    return blocks


def data_distinct_values(
    principal: Principal, client_id: int, dataset: str, column: str, tax_years: Any = None, limit: int = DEFAULT_DISTINCT,
) -> ToolResult:
    """The distinct values of one category column for a client, so a filter can be written without guessing."""
    try:
        _listable(dataset, column)
        result = service().run(_values_spec(client_id, dataset, column, tax_years, limit), principal=asker(principal),
                               suppress_small_groups=suppress_small_groups(principal))
    except QueryError as exc:
        raise refused(exc) from exc
    values = _merge(result.columns, result.rows, column)
    p = result.provenance
    truncated = p.truncated or len(values) > limit
    values = values[:limit]
    facts = {
        "dataset": dataset, "column": column, "client_id": client_id, "tax_years": list(p.tax_years),
        "value_count": len(values), "truncated": truncated, "row_limit": limit, "values": values,
        "source": p.source_line, "notes": list(p.notes),
        **({"small_groups": dict(p.small_groups)} if p.small_groups else {}),
    }
    return s.result(
        "data_distinct_values", facts, _values_blocks(dataset, column, values, truncated, p.source_line),
        provenance=Provenance(run_id=p.run.run_id if p.run else None, source=p.source_line),
        warnings=p.notes,
    )
