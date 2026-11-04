"""The WHERE clause: client scope first, then currency, years, method and the caller's filters. [CH-16b]

Order is the point. The client predicate is the first term of every WHERE (and every JOIN's
ON), written as the `{tenant}` marker that `infrastructure/persistence/tenant_sql.py`
rewrites to a bound `client_id = ?` and refuses to run without. A statement that reaches a
cursor therefore cannot return another client's rows, whatever else is in it, and the
builder cannot be the thing that forgot.

Every value is a `?` placeholder; the only literals in the text are the model's own
column names and fixed keywords. Params are returned in the order their placeholders
appear, which is what both drivers bind by.
"""
from __future__ import annotations

from functools import partial
from typing import Any

from application.data.dialect import Dialect, SchemaNames, bind_value, column_sql, quote, table_name
from application.data.plan import BASE_ALIAS, FilterPlan, Plan
from application.data.semantic_model import Currency, Dataset, Op, SchemaKey
from application.data.values import escape_like

Fragment = tuple[str, list[Any]]

#: A LIKE escape written as a SQL literal; contains no placeholder, so the tenant helper's count is unaffected.
LIKE_ESCAPE = " ESCAPE '\\'"


def tenant_marker(dataset: Dataset, alias: str) -> str:
    """The tenant-helper marker for `alias`, naming the table's client column where it is not `client_id`."""
    column = "" if dataset.tenant_column == "client_id" else f"@{dataset.tenant_column}"
    return f"{{tenant:{alias}{column}}}"


def where_clause(plan: Plan, dialect: Dialect, schemas: SchemaNames) -> Fragment:
    """`WHERE {tenant:t} AND ...` and its params, in placeholder order."""
    terms: list[Fragment] = [(tenant_marker(plan.dataset, BASE_ALIAS), [])]
    for fragment in (_currency(plan, dialect, schemas), _years(plan, dialect), _method(plan, dialect)):
        if fragment is not None:
            terms.append(fragment)
    terms.extend(_filter(f, dialect) for f in plan.filters)
    return "WHERE " + " AND ".join(t for t, _ in terms), [p for _, ps in terms for p in ps]


def _currency(plan: Plan, dialect: Dialect, schemas: SchemaNames) -> Fragment | None:
    """Read only the live rows: the current row, or the rows of the client's live run."""
    q = partial(quote, dialect)
    if plan.dataset.currency is Currency.IS_CURRENT:
        return f"{BASE_ALIAS}.{q('is_current')} = ?", [1]
    if plan.dataset.currency is not Currency.LIVE_RUN:
        return None
    manifest = table_name(dialect, schemas.name(SchemaKey.OPS), "run_manifest")
    limit_top = "TOP 1 " if dialect is Dialect.TSQL else ""
    limit_tail = " LIMIT 1" if dialect is Dialect.SQLITE else ""
    inner = (
        f"(SELECT {limit_top}m.{q('run_id')} FROM {manifest} AS m WHERE {{tenant:m}} "
        f"AND m.{q('run_status')} = ? AND m.{q('superseded_by_run_id')} IS NULL "
        f"AND m.{q('run_completed_at')} IS NOT NULL ORDER BY m.{q('run_started_at')} DESC{limit_tail})"
    )
    return f"{BASE_ALIAS}.{q('run_id')} = {inner}", ["success"]


def _years(plan: Plan, dialect: Dialect) -> Fragment | None:
    if not plan.tax_years:
        return None
    expr = column_sql(dialect, plan.dataset.column(plan.dataset.year_column), BASE_ALIAS)
    if len(plan.tax_years) == 1:
        return f"{expr} = ?", [plan.tax_years[0]]
    return f"{expr} IN ({', '.join('?' for _ in plan.tax_years)})", list(plan.tax_years)


def _method(plan: Plan, dialect: Dialect) -> Fragment | None:
    """`both` adds no predicate; a named reading pins the method column."""
    if plan.method not in ("min_max", "pay_period"):
        return None
    expr = column_sql(dialect, plan.dataset.column(plan.dataset.method_column), BASE_ALIAS)
    return f"{expr} = ?", [plan.method]


def _filter(item: FilterPlan, dialect: Dialect) -> Fragment:
    expr = column_sql(dialect, item.ref.column, item.ref.alias)
    value = item.value
    if item.op is Op.EQ:
        return f"{expr} = ?", [bind_value(dialect, value)]
    if item.op is Op.IN:
        return f"{expr} IN ({', '.join('?' for _ in value)})", [bind_value(dialect, v) for v in value]
    if item.op is Op.BETWEEN:
        return f"{expr} BETWEEN ? AND ?", [bind_value(dialect, v) for v in value]
    if item.op is Op.CONTAINS:
        return f"LOWER({expr}) LIKE ?{LIKE_ESCAPE}", [f"%{escape_like(value.lower())}%"]
    return f"{expr} {'>=' if item.op is Op.GTE else '<='} ?", [bind_value(dialect, value)]
