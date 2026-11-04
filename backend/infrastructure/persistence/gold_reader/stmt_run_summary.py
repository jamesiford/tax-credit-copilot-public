"""What only the run knew: per-method summaries, the year series and the One/Zero matrix."""
from __future__ import annotations

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import Statement


def _stmt_method_summary(client_id: int, tax_year: int, method: str, run_id: str) -> Statement:
    return (
        f"SELECT TOP 1 * FROM {GOLD_SCHEMA}.run_method_summary "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ?",
        [client_id, tax_year, method, run_id],
    )


def _stmt_month_totals(client_id: int, tax_year: int, method: str, run_id: str) -> Statement:
    """The twelve monthly headcount totals, summed across every unit.

    `_ytd_average_headcount` walked `OneZeroResult.summary` to get these, which
    cost a replay of the whole payroll. `unit_month_summary` is that summary,
    already written by the run.
    """
    sums = ", ".join(f"SUM(month_{index:02d}) AS month_{index:02d}" for index in range(1, 13))
    # Unreachable months are a fact about the YEAR's pay calendar, written
    # identically on every unit row of it, so MAX reads the one value.
    return (
        f"SELECT {sums}, MAX(unreachable_months) AS unreachable_months "
        f"FROM {GOLD_SCHEMA}.unit_month_summary "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ?",
        [client_id, tax_year, method, run_id],
    )


def _stmt_client_year_series(client_id: int, method: str, run_id: str) -> Statement:
    """Every year the run reached, with what each one concluded.

    Answers "how have they moved since their base year" from one statement.
    `run_method_summary` is per client-year-method, so the series is a straight
    read — the alternative is a replay per year, which is what this whole
    workstream exists to remove.
    """
    return (
        f"SELECT tax_year, annual_average, eligible_employees, employees_evaluated, "
        f"  contested_months "
        f"FROM {GOLD_SCHEMA}.run_method_summary "
        f"WHERE client_id = ? AND method = ? AND run_id = ? "
        f"ORDER BY tax_year",
        [client_id, method, run_id],
    )


def _stmt_client_year_credit(client_id: int, method: str) -> Statement:
    """Credit and base-year flags per year, summed across the client's units.

    `qualified` is a BIT, so the count of qualifying units must NOT borrow that
    name: `_coerce` types by column name and would hand back `True`. Same trap
    as the eligible count.
    """
    return (
        f"SELECT tax_year, SUM(annual_credit_usd) AS annual_credit_usd, "
        f"  MAX(CAST(is_base_year AS INT)) AS has_base_year, "
        f"  SUM(CAST(qualified AS INT)) AS qualified_units, COUNT(*) AS units "
        f"FROM {GOLD_SCHEMA}.unit_year_master "
        f"WHERE client_id = ? AND method = ? AND is_current = 1 "
        f"GROUP BY tax_year ORDER BY tax_year",
        [client_id, method],
    )


def _stmt_onezero_matrix(client_id: int, tax_year: int, method: str, run_id: str) -> Statement:
    months = ", ".join(f"month_{index:02d}" for index in range(1, 13))
    return (
        f"SELECT employee_id, record_token, worksite_id, entity_fein, weight, {months} "
        f"FROM {GOLD_SCHEMA}.onezero_matrix "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ? "
        f"ORDER BY worksite_id, employee_id",
        [client_id, tax_year, method, run_id],
    )


def _stmt_unit_fein_summary(client_id: int, tax_year: int, method: str, run_id: str) -> Statement:
    """The unit x FEIN roll-up, summed in SQL.

    `unit_month_summary` is per worksite; the screen groups by worksite AND
    entity, which the matrix carries. Summed here rather than in Python so the
    twelve month columns are added once, by the engine that stored them.

    Two details reproduce `rollup_matrix_by_two_fields` rather than improving on
    it, because the screen has always rendered its output:

    * **The average is rounded to 2dp.** Unrounded, `total / 12` renders
      25.916666666 where the grid has always shown 25.92.
    * **A missing worksite or FEIN reads `(unattributed)`, not NULL.** The
      rollup has always said so out loud, and a blank cell in a column that
      names a legal entity is the wrong kind of quiet.

    `weight` is deliberately NOT applied: the stored month values already carry
    it, and multiplying again would halve a part-timer twice.
    """
    months = ", ".join(
        f"SUM(m.month_{index:02d}) AS month_{index:02d}" for index in range(1, 13)
    )
    total = " + ".join(f"SUM(m.month_{index:02d})" for index in range(1, 13))
    return (
        f"SELECT COALESCE(NULLIF(m.worksite_id, ''), '(unattributed)') AS worksite_id, "
        f"  COALESCE(NULLIF(m.entity_fein, ''), '(unattributed)') AS entity_fein, "
        f"  {months}, {total} AS total, "
        f"  ROUND(({total}) / 12.0, 2) AS average_headcount "
        f"FROM {GOLD_SCHEMA}.onezero_matrix AS m "
        f"WHERE m.client_id = ? AND m.tax_year = ? AND m.method = ? AND m.run_id = ? "
        f"GROUP BY COALESCE(NULLIF(m.worksite_id, ''), '(unattributed)'), "
        f"  COALESCE(NULLIF(m.entity_fein, ''), '(unattributed)') "
        f"ORDER BY worksite_id, entity_fein",
        [client_id, tax_year, method, run_id],
    )


def _stmt_client_year_rows(client_id: int, tax_year: int, method: str) -> Statement:
    """Does Gold hold anything for this client-year at all?

    Separates "we never calculated this year" from "that unit id is unknown".
    Both leave the unit row empty, and only the second is a 404.
    """
    return (
        f"SELECT COUNT(*) AS total FROM {GOLD_SCHEMA}.unit_year_master "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND is_current = 1",
        [client_id, tax_year, method],
    )
