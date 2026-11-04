"""The unit grid: one row per location-year, its month columns, credit stream and totals."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import Statement, UNIT_YEAR_MASTER_COLUMNS


def _unit_year_where(
    client_id: int, method: str, tax_year: int | None, program_code: str | None, alias: str = ""
) -> Statement:
    p = f"{alias}." if alias else ""
    where = f"{p}client_id = ? AND {p}is_current = 1 AND {p}method = ?"
    values: list[Any] = [client_id, method]
    if tax_year is not None:
        where += f" AND {p}tax_year = ?"
        values.append(tax_year)
    if program_code:
        where += f" AND {p}program_code = ?"
        values.append(program_code)
    return where, values


def _stmt_unit_years_count(
    client_id: int, method: str, tax_year: int | None, program_code: str | None
) -> Statement:
    where, values = _unit_year_where(client_id, method, tax_year, program_code, "m")
    return f"SELECT COUNT(*) AS total FROM {GOLD_SCHEMA}.unit_year_master m WHERE {where}", values


def _stmt_unit_years(
    client_id: int, method: str, tax_year: int | None, program_code: str | None,
    limit: int, offset: int,
) -> Statement:
    where, values = _unit_year_where(client_id, method, tax_year, program_code, "m")
    selected = ", ".join(f"m.{column}" for column in UNIT_YEAR_MASTER_COLUMNS)
    return (
        f"SELECT {selected}, s.months_with_headcount, s.unreachable_months "
        f"FROM {GOLD_SCHEMA}.unit_year_master m "
        f"LEFT JOIN {GOLD_SCHEMA}.unit_month_summary s "
        f"  ON s.client_id = m.client_id AND s.tax_year = m.tax_year "
        f" AND s.method = m.method AND s.worksite_id = m.worksite_id "
        f" AND s.run_id = m.run_id "
        f"WHERE {where} "
        f"ORDER BY m.worksite_id, m.tax_year "
        f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        [*values, int(offset), int(limit)],
    )


def _stmt_month_summaries(
    client_id: int, method: str, run_id: str, tax_year: int | None
) -> Statement:
    statement = (
        f"SELECT * FROM {GOLD_SCHEMA}.unit_month_summary "
        f"WHERE client_id = ? AND method = ? AND run_id = ?"
    )
    values: list[Any] = [client_id, method, run_id]
    if tax_year is not None:
        statement += " AND tax_year = ?"
        values.append(tax_year)
    return statement + " ORDER BY worksite_id, tax_year", values


def _stmt_credit_columns(client_id: int, method: str, program_code: str | None) -> Statement:
    where, values = _unit_year_where(client_id, method, None, program_code)
    return (
        f"SELECT worksite_id, tax_year, SUM(claimable_usd) AS claimable_usd, "
        f"MAX(CAST(projected AS INT)) AS projected, MIN(creation_year) AS creation_year "
        f"FROM {GOLD_SCHEMA}.unit_credit_installment WHERE {where} "
        f"GROUP BY worksite_id, tax_year ORDER BY worksite_id, tax_year",
        values,
    )


def _stmt_unit_totals(client_id: int, method: str, program_code: str | None) -> Statement:
    where, values = _unit_year_where(client_id, method, None, program_code)
    return (
        f"SELECT worksite_id, SUM(annual_credit_usd) AS total_annual_credit_usd, "
        f"MAX(high_water_mark) AS final_high_water_mark "
        f"FROM {GOLD_SCHEMA}.unit_year_master WHERE {where} "
        f"GROUP BY worksite_id ORDER BY worksite_id",
        values,
    )


def _stmt_unit_lifetime(client_id: int, method: str, program_code: str | None) -> Statement:
    where, values = _unit_year_where(client_id, method, None, program_code)
    return (
        f"SELECT worksite_id, SUM(claimable_usd) AS total_tranche_lifetime_usd "
        f"FROM {GOLD_SCHEMA}.unit_credit_installment WHERE {where} "
        f"GROUP BY worksite_id",
        values,
    )


#: The month-grain columns the grid draws. `average_headcount` is aliased on
#: the way out: `unit_year_master` has a column of the same name and the join
#: would make it ambiguous.
_MONTH_COLUMNS = tuple(f"month_{index:02d}" for index in range(1, 13))


def _stmt_unit_grid(
    client_id: int, method: str, program_code: str | None, limit: int, offset: int
) -> Statement:
    """The whole grid in ONE statement: rows, months, per-unit totals, count.

    Replaces four separate statements. `unit_year_master` and
    `unit_month_summary` were already joined here; the per-unit money and the
    paging count were re-deriving the SAME row set in two more scans, which is
    what window functions are for.

    This is only equivalent to those statements when the caller has NOT asked
    for a single tax year: the totals span every year a unit has, while a
    year-filtered window would only see one. `unit_page` keeps the older path
    for that case rather than quietly narrowing the money.
    """
    where, values = _unit_year_where(client_id, method, None, program_code, "m")
    selected = ", ".join(f"m.{column}" for column in UNIT_YEAR_MASTER_COLUMNS)
    months = ", ".join(f"s.{column}" for column in _MONTH_COLUMNS)
    return (
        f"SELECT {selected}, {months}, "
        f"s.total AS month_total, s.months_with_headcount, s.unreachable_months, "
        f"s.average_headcount AS month_average_headcount, "
        f"SUM(m.annual_credit_usd) OVER (PARTITION BY m.worksite_id) "
        f"    AS total_annual_credit_usd, "
        f"MAX(m.high_water_mark) OVER (PARTITION BY m.worksite_id) "
        f"    AS final_high_water_mark, "
        f"COUNT(*) OVER () AS total_rows "
        f"FROM {GOLD_SCHEMA}.unit_year_master m "
        f"LEFT JOIN {GOLD_SCHEMA}.unit_month_summary s "
        f"  ON s.client_id = m.client_id AND s.tax_year = m.tax_year "
        f" AND s.method = m.method AND s.worksite_id = m.worksite_id "
        f" AND s.run_id = m.run_id "
        f"WHERE {where} "
        f"ORDER BY m.worksite_id, m.tax_year "
        f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        [*values, int(offset), int(limit)],
    )


def _stmt_credit_grid(client_id: int, method: str, program_code: str | None) -> Statement:
    """Claimable dollars per unit-year, carrying each unit's lifetime total.

    The lifetime sum used to be its own scan of the same table. Summing the
    group sums in a window costs nothing extra.
    """
    where, values = _unit_year_where(client_id, method, None, program_code)
    return (
        f"SELECT worksite_id, tax_year, SUM(claimable_usd) AS claimable_usd, "
        f"MAX(CAST(projected AS INT)) AS projected, MIN(creation_year) AS creation_year, "
        f"SUM(SUM(claimable_usd)) OVER (PARTITION BY worksite_id) "
        f"    AS total_tranche_lifetime_usd "
        f"FROM {GOLD_SCHEMA}.unit_credit_installment WHERE {where} "
        f"GROUP BY worksite_id, tax_year ORDER BY worksite_id, tax_year",
        values,
    )


def _stmt_unit(client_id: int, worksite_id: str, tax_year: int, method: str) -> Statement:
    return (
        f"SELECT TOP 1 {', '.join(UNIT_YEAR_MASTER_COLUMNS)} "
        f"FROM {GOLD_SCHEMA}.unit_year_master "
        f"WHERE client_id = ? AND worksite_id = ? AND tax_year = ? "
        f"AND method = ? AND is_current = 1",
        [client_id, worksite_id, tax_year, method],
    )


def _stmt_unit_months(
    client_id: int, worksite_id: str, tax_year: int, method: str, run_id: str
) -> Statement:
    return (
        f"SELECT TOP 1 * FROM {GOLD_SCHEMA}.unit_month_summary "
        f"WHERE client_id = ? AND worksite_id = ? AND tax_year = ? "
        f"AND method = ? AND run_id = ?",
        [client_id, worksite_id, tax_year, method, run_id],
    )
