"""The SQL the source reads run, built from the mapping rather than spelled out. [06.2]

Every table and column comes from `data.source.mapping`, quoted, so a renamed column, a prefix, a casing
difference or a reserved word (`union`) changes a file and no statement. The semantics each statement must
share with the Python projection (`to_bcs.source_to_bcs_rows`) are stated beside the expression that carries
them, and the named transforms (`worksite_location`, `null_pay_date`) have a SQL form here and a Python form
there; `tests/test_source_sql_scope.py` asserts the two agree.
"""
from __future__ import annotations

from typing import Callable

from data.source.book_keys import BOOK_FIELDS
from data.source.mapping import null_pay_date_mode, quoted, worksite_mode
from data.source.mapping.transforms import pay_date_sql, worksite_sql

TableRef = Callable[[str], str]


def pay_date() -> str:
    """The effective pay date: the period end stands in for a null one under `period_end`, nothing under `exclude`."""
    return pay_date_sql(null_pay_date_mode(), quoted("Payroll", "pay_date", "p"), quoted("Payroll", "pay_period_end", "p"))


def has_span() -> str:
    """The row population: `source_to_bcs_rows` skips a period with no span (and, under `exclude`, a null pay date)."""
    start, end = quoted("Payroll", "pay_period_start", "p"), quoted("Payroll", "pay_period_end", "p")
    base = f"{start} IS NOT NULL AND {end} IS NOT NULL"
    return base + (f" AND {pay_date()} IS NOT NULL" if null_pay_date_mode() == "exclude" else "")


def tax_year() -> str:
    """`Tax_Year` in the projection is the pay date's year (the period end's when the pay date is null)."""
    return f"YEAR({pay_date()})"


def state() -> str:
    """Location -> Address -> StateCountyZip; the Python `or` chain treats '' as missing, so '' is nulled first."""
    abbr, original = quoted("StateCountyZip", "state_abbr", "s"), quoted("Address", "state_original", "a")
    return f"UPPER(COALESCE(NULLIF({abbr}, ''), NULLIF({original}, ''), ''))"


def location() -> str:
    """Which location a row's jobs are counted at (the `worksite_location` transform, open question Q3)."""
    return worksite_sql(worksite_mode(), quoted("Payroll", "worksite_location_id", "p"), quoted("Payroll", "location_id", "p"))


def payroll_joins(table: TableRef) -> str:
    """Payroll `p` with its location `l`, address `a` and state-county-zip `s`, as outer joins."""
    q = quoted
    return (
        f"FROM {table('Payroll')} p "
        f"LEFT JOIN {table('Location')} l ON {q('Location', 'location_id', 'l')} = {location()} "
        f"LEFT JOIN {table('Address')} a ON {q('Address', 'address_id', 'a')} = {q('Location', 'address_id', 'l')} "
        f"LEFT JOIN {table('StateCountyZip')} s "
        f"ON {q('StateCountyZip', 'state_county_zip_id', 's')} = {q('Address', 'state_county_zip_id', 'a')}"
    )


def accounts(table: TableRef) -> tuple[str, tuple[str, ...]]:
    """The client-book select and the keys its columns come back as; an unmapped optional field reads NULL."""
    fields = BOOK_FIELDS
    parts = []
    for field_name, _ in fields:
        try:
            parts.append(quoted("Account", field_name))
        except Exception:  # noqa: BLE001 - only an optional field the mapping dropped reaches here; it reads as NULL
            parts.append("NULL")
    return f"SELECT {', '.join(parts)} FROM {table('Account')}", tuple(key for _, key in fields)


def payroll_scope(table: TableRef) -> str:
    """Years, states and pay dates for one client (`?` is the account id), grouped so they share one scan."""
    tenant = quoted("Payroll", "account_id", "p")
    return (
        f"SELECT {tax_year()} AS tax_year, {state()} AS work_state, {pay_date()} AS pay_date, COUNT_BIG(*) AS rows_in "
        f"{payroll_joins(table)} WHERE {tenant} = ? AND {has_span()} "
        f"GROUP BY {tax_year()}, {state()}, {pay_date()}"
    )


def footprint(table: TableRef) -> str:
    """Which states each client holds payroll in: one `GROUP BY` over payroll, for every client."""
    tenant = quoted("Payroll", "account_id", "p")
    return f"SELECT {tenant} AS account_id, {state()} AS work_state {payroll_joins(table)} WHERE {has_span()} GROUP BY {tenant}, {state()}"


def fiscal_rules(table: TableRef) -> str:
    """One client's fiscal rules, reached through `Entity` (`?` is the account id), in a stable order."""
    r, e = "r", "e"
    cols = ", ".join(quoted("EntityFiscalYearRules", f, r) for f in (
        "fiscal_year_rules_id", "name", "fiscal_year_begin", "fiscal_year_end", "rule_expression", "inferred"))
    key = quoted("EntityFiscalYearRules", "fiscal_year_rules_id", r)
    return (
        f"SELECT DISTINCT {cols} FROM {table('EntityFiscalYearRules')} {r} "
        f"JOIN {table('Entity')} {e} ON {quoted('Entity', 'fiscal_year_rules_id', e)} = {key} "
        f"WHERE {quoted('Entity', 'account_id', e)} = ? ORDER BY {key}"
    )
