"""Build a parameterised statement from a specification and the semantic model. [CH-16b]

`build_sql(spec, model, dialect)` returns `(sql, params)`. What that promises:

- **Only model-authored text is interpolated**: physical table and column names (plain
  identifiers, quoted), the deployed schema names (validated identifiers), fixed keywords,
  a derived column's reviewed expression, a measure alias that matched a strict pattern, and
  the row limit as an integer. A caller's string never becomes SQL.
- **Every value is a bound parameter.** Placeholders and params correspond one to one.
- **The statement carries the `{tenant}` marker, not a client id.** The executor runs it
  through `TenantScopedQuery(plan.client_id)`, which binds the client and refuses a statement
  where the marker is not the first term of a WHERE or ON. So the client scope is the first
  predicate everywhere, including the live-run subquery and every join.
- **Row order is deterministic**: the caller's ordering, then every selected column, so a
  tie never depends on how the engine happens to scan.
- **One more row than asked for is fetched** (`TRUNCATION_PROBE`), so an executor can say the
  result was capped without a second COUNT, and drops the extra row.

SELECT-only by construction: there is no code path here that emits anything else.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from application.data.build_where import tenant_marker, where_clause
from application.data.dialect import (
    DEFAULT_SCHEMAS, Dialect, SchemaNames, cast_for_avg, cast_for_sum, column_sql, quote, table_name,
)
from application.data.plan import BASE_ALIAS, ColumnRef, MeasurePlan, Plan
from application.data.semantic_model import Agg, SemanticModel
from application.data.spec import QuerySpec
from application.data.validate import validate

#: Rows fetched beyond the limit, to detect truncation.
TRUNCATION_PROBE = 1


@dataclass(frozen=True, slots=True)
class BuiltQuery:
    """A statement in tenant-marker form, its params in placeholder order, and the plan it came from."""

    sql: str
    params: list[Any]
    plan: Plan
    dialect: Dialect

    def as_tuple(self) -> tuple[str, list[Any]]:
        """The `(sql, params)` pair."""
        return self.sql, self.params


def build_sql(spec: QuerySpec, model: SemanticModel, dialect: Dialect, schemas: SchemaNames = DEFAULT_SCHEMAS,
              *, known_years: Collection[int] | None = None) -> tuple[str, list[Any]]:
    """`(sql, params)` for a specification, after validating it. Raises a `QueryError` if it may not run."""
    return build_query(spec, model, dialect, schemas, known_years=known_years).as_tuple()


def build_query(spec: QuerySpec, model: SemanticModel, dialect: Dialect, schemas: SchemaNames = DEFAULT_SCHEMAS,
                *, known_years: Collection[int] | None = None) -> BuiltQuery:
    """Validate, then build; the plan travels with the statement for provenance and audience."""
    plan = validate(spec, model, known_years=known_years)
    return BuiltQuery(*_statement(plan, dialect, schemas), plan=plan, dialect=dialect)


def _statement(plan: Plan, dialect: Dialect, schemas: SchemaNames) -> tuple[str, list[Any]]:
    fetch = plan.limit + TRUNCATION_PROBE
    top = f"TOP ({fetch}) " if dialect is Dialect.TSQL else ""
    where, params = where_clause(plan, dialect, schemas)
    parts = [f"SELECT {top}{', '.join(_select_items(plan, dialect))}", _from(plan, dialect, schemas), where]
    if plan.group_by:
        parts.append("GROUP BY " + ", ".join(column_sql(dialect, r.column, r.alias) for r in plan.group_by))
    order = _order_items(plan, dialect)
    if order:
        parts.append("ORDER BY " + ", ".join(order))
    if dialect is Dialect.SQLITE:
        parts.append(f"LIMIT {fetch}")
    return " ".join(parts), params


def _select_items(plan: Plan, dialect: Dialect) -> list[str]:
    dims = [f"{column_sql(dialect, r.column, r.alias)} AS {quote(dialect, r.label)}" for r in plan.select]
    return dims + [f"{_aggregate(m, dialect)} AS {quote(dialect, m.alias)}" for m in plan.measures]


def _aggregate(measure: MeasurePlan, dialect: Dialect) -> str:
    if measure.ref is None:
        return "COUNT(*)"
    expr = column_sql(dialect, measure.ref.column, measure.ref.alias)
    kind = measure.ref.column.type
    if measure.agg is Agg.SUM:
        return cast_for_sum(expr, kind)
    if measure.agg is Agg.AVG:
        return cast_for_avg(dialect, expr, kind)
    if measure.agg is Agg.COUNT_DISTINCT:
        return f"COUNT(DISTINCT {expr})"
    return f"{measure.agg.value.upper()}({expr})"


def _from(plan: Plan, dialect: Dialect, schemas: SchemaNames) -> str:
    dataset = plan.dataset
    text = f"FROM {table_name(dialect, schemas.name(dataset.schema), dataset.table)} AS {BASE_ALIAS}"
    for joined in plan.joins:
        name, target = joined.decl.name, joined.target
        on = " AND ".join(
            f"{BASE_ALIAS}.{quote(dialect, dataset.column(a).physical)} = {name}.{quote(dialect, target.column(b).physical)}"
            for a, b in joined.decl.on
        )
        table = table_name(dialect, schemas.name(target.schema), target.table)
        text += f" LEFT JOIN {table} AS {name} ON {tenant_marker(target, name)} AND {on}"
    return text


def _order_items(plan: Plan, dialect: Dialect) -> list[str]:
    items, seen = [], set()
    for order in plan.order_by:
        seen.add(order.label)
        key = column_sql(dialect, order.ref.column, order.ref.alias) if order.ref else quote(dialect, order.label)
        items.append(f"{key} {order.direction.upper()}")
    for ref in plan.group_by or plan.select:
        if ref.label not in seen:
            items.append(f"{column_sql(dialect, ref.column, ref.alias)} ASC")
    return items
