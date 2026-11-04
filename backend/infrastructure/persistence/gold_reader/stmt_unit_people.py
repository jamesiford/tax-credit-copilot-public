"""The people at one location: the counted employees and the near-threshold cohort, sorted and filtered."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import Statement
from tools.grid_filter import compile_filters


#: Sortable employee columns, mapped to the SQL that orders them. A whitelist
#: rather than interpolation: the value arrives from a query string.
_EMPLOYEE_SORTS = {
    "avg_weekly_hours": "e.avg_weekly_hours",
    "avg_weekly_wages": "e.avg_weekly_wages",
    "employee_id": "m.employee_id",
}

#: Same columns on the near-threshold statement, which reads `employee_eligibility`
#: alone and so has no `m` alias.
_NEAR_SORTS = {
    "avg_weekly_hours": "e.avg_weekly_hours",
    "avg_weekly_wages": "e.avg_weekly_wages",
    "employee_id": "e.employee_id",
    "weeks_worked": "e.weeks_worked",
    "total_hours": "e.total_hours",
}

#: Filterable employee columns, as (SQL expression, grammar type). The whitelist
#: is what makes `filter=` safe to accept from a query string: a name absent
#: here never reaches the statement, and every value is bound.
EMPLOYEE_FILTERS = {
    "employee_id": ("m.employee_id", "text"),
    "avg_weekly_hours": ("e.avg_weekly_hours", "numeric"),
    "avg_weekly_wages": ("e.avg_weekly_wages", "numeric"),
    "weeks_worked": ("e.weeks_worked", "numeric"),
    "total_hours": ("e.total_hours", "numeric"),
    "weight": ("m.weight", "numeric"),
}

NEAR_FILTERS = {
    "employee_id": ("e.employee_id", "text"),
    "avg_weekly_hours": ("e.avg_weekly_hours", "numeric"),
    "avg_weekly_wages": ("e.avg_weekly_wages", "numeric"),
    "weeks_worked": ("e.weeks_worked", "numeric"),
    "total_hours": ("e.total_hours", "numeric"),
}


def _order_by(sorts: dict[str, str], sort: str | None, order: str | None, tiebreak: str) -> str:
    column = sorts.get((sort or "").strip()) or sorts["avg_weekly_hours"]
    direction = "ASC" if (order or "").strip().lower() == "asc" else "DESC"
    # A stable tiebreak, or two reads of the same sort can repeat or drop a row.
    # Omitted when it IS the sort column: SQL Server rejects a column named
    # twice in one ORDER BY, which turned `sort=employee_id` into a 500.
    if column == tiebreak:
        return f" ORDER BY {column} {direction}"
    return f" ORDER BY {column} {direction}, {tiebreak}"


def _stmt_unit_employees(
    client_id: int, worksite_id: str, tax_year: int, method: str, run_id: str,
    month: int | None, sort: str | None = None, order: str | None = None,
    limit: int | None = None, filters: str | None = None,
    count_only: bool = False,
) -> Statement:
    months = ", ".join(f"m.month_{index:02d}" for index in range(1, 13))
    top = f"TOP {int(limit)} " if limit and not count_only else ""
    selected = (
        "COUNT(*) AS total "
        if count_only
        else (
            f"{top}m.employee_id, m.record_token, m.worksite_id, m.entity_fein, "
            f"m.first_pps, m.last_ppe, m.weight, {months}, "
            f"e.avg_weekly_hours, e.avg_weekly_wages, e.weeks_worked, e.total_hours, "
            f"e.total_wages, e.first_start, e.last_end "
        )
    )
    statement = (
        f"SELECT {selected}"
        f"FROM {GOLD_SCHEMA}.onezero_matrix AS m "
        f"LEFT JOIN {GOLD_SCHEMA}.employee_eligibility AS e "
        f"  ON e.record_token = m.record_token AND e.client_id = m.client_id "
        f" AND e.tax_year = m.tax_year AND e.method = m.method AND e.run_id = m.run_id "
        f"WHERE m.client_id = ? AND m.worksite_id = ? AND m.tax_year = ? "
        f"AND m.method = ? AND m.run_id = ?"
    )
    values: list[Any] = [client_id, worksite_id, tax_year, method, run_id]
    if month is not None:
        statement += f" AND m.month_{int(month):02d} > 0"
    # Filtering happens HERE, not after the fetch. Candle Bottle holds 10,236
    # employees across 101 units; narrowing in Python is the same problem one
    # layer up from where it was already fixed for sorting.
    clause, params, _ = compile_filters(filters, EMPLOYEE_FILTERS)
    statement += clause
    values.extend(params)
    if count_only:
        return statement, values
    return statement + _order_by(_EMPLOYEE_SORTS, sort, order, "m.employee_id"), values


def _stmt_unit_near_threshold(
    client_id: int, worksite_id: str, tax_year: int, method: str, run_id: str,
    sort: str | None = None, order: str | None = None,
    near_min_hours: float | None = None, limit: int | None = None,
    filters: str | None = None, count_only: bool = False,
) -> Statement:
    top = f"TOP {int(limit)} " if limit and not count_only else ""
    selected = (
        "e.record_token "
        if count_only
        else (
            f"{top}e.employee_id, e.record_token, "
            f"e.avg_weekly_hours, e.avg_weekly_wages, e.weeks_worked, "
            f"e.total_hours, e.total_wages, e.first_start, e.last_end "
        )
    )
    statement = (
        f"SELECT DISTINCT {selected}"
        f"FROM {GOLD_SCHEMA}.employee_eligibility AS e "
        f"JOIN {GOLD_SCHEMA}.employee_period_fact AS p "
        f"  ON p.record_token = e.record_token AND p.client_id = e.client_id "
        f" AND p.tax_year = e.tax_year "
        f"WHERE e.client_id = ? AND e.tax_year = ? AND e.method = ? "
        f"AND e.run_id = ? AND e.eligible = 0 AND p.worksite_id = ?"
    )
    values: list[Any] = [client_id, tax_year, method, run_id, worksite_id]
    if near_min_hours is not None:
        # The band arrives as an ABSOLUTE hours floor, computed by the caller
        # from the statutory minimum it was already given. A literal here would
        # bake Georgia's 35 into every other jurisdiction's warehouse read.
        statement += " AND e.avg_weekly_hours >= ?"
        values.append(float(near_min_hours))
    clause, params, _ = compile_filters(filters, NEAR_FILTERS)
    statement += clause
    values.extend(params)
    if count_only:
        # DISTINCT has to be counted through a derived table. There is no
        # ORDER BY inside it, which is what SQL Server would reject.
        return f"SELECT COUNT(*) AS total FROM ({statement}) AS cohort", values
    return statement + _order_by(_NEAR_SORTS, sort, order, "e.employee_id"), values
