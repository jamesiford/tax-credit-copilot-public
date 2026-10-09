"""Reading `tcc_gold`. The screens' only source of figures.

The counterpart to `warehouse_gold.GoldWriter`. A run writes; every read comes
here. No calculation happens on a page load — if a client has not been
calculated, that is an answer, not a reason to compute one.

Three states, and they are modelled rather than inferred:

  * **calculated**      a live run exists, and its rows are returned.
  * **not_calculated**  no live run exists. `run` is None and `items` is empty
                        BECAUSE NOTHING HAS RUN. Callers must render this as an
                        invitation to run the calculation.
  * **calculated, zero** a live run exists and legitimately produced no rows.
                        `run` is populated and `items` is empty.

The last two look identical on `total` alone, which is why `run` is the
discriminator and `calculation_state` says it out loud. Collapsing them puts
"this client has no payroll" on screen for a client nobody has assessed yet.

Money is returned as a STRING, never a float. JSON has no decimal type, and
`Decimal("12345678.91")` serialised as a JSON number comes back
`12345678.909999999`. Headcount is a measurement rather than money and stays a
float, which is the same split the Gold schema itself makes.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Sequence

from infrastructure.persistence.fabric_warehouse import (
    GOLD_SCHEMA,
    OPS_SCHEMA,
    STRANDED_RUN_MINUTES,
    FabricWarehouseConnection,
)
from tools.grid_filter import compile_filters

#: Every column of `unit_year_master`, in DDL order. The audit found 13 of 34
#: reaching the API and `per_job_usd` missing, so a dollar could not be checked
#: from its own row. Listing them here is what closes that.
UNIT_YEAR_MASTER_COLUMNS: tuple[str, ...] = (
    "client_id", "worksite_id", "entity_fein", "program_code", "method",
    "tax_year", "average_headcount", "is_base_year", "base_average_headcount",
    "base_year_source", "net_new_vs_base", "months_reachable", "year_complete",
    "declined", "decline_reason", "threshold", "threshold_source", "qualified",
    "status", "tier", "designation", "tier_source", "eligible_jobs",
    "new_jobs_created", "high_water_mark", "backfilled", "per_job_usd",
    "tranche_years", "annual_credit_usd", "base_year_overridden",
    "high_water_mark_overridden", "run_id", "is_current", "appended_at",
)

#: DECIMAL(19,4) columns — money. Serialised as strings.
#:
#: The SQL aggregate ALIASES belong here too. `SUM(annual_credit_usd)` comes
#: back as a Decimal under the name `total_annual_credit_usd`, and a name this
#: set does not know falls through to the float branch — which is how a summed
#: figure loses the exactness every row that fed it had.
_MONEY_COLUMNS = frozenset({
    "per_job_usd", "annual_credit_usd", "claimable_usd",
    "identified_usd", "claimed_usd", "certified_usd",
    "total_annual_credit_usd", "total_tranche_lifetime_usd",
})

#: BIT columns. pyodbc hands back 0/1 or True/False depending on driver build.
_BOOL_COLUMNS = frozenset({
    "is_base_year", "year_complete", "declined", "qualified", "backfilled",
    "base_year_overridden", "high_water_mark_overridden", "is_current",
    "eligible", "projected",
})

_MANIFEST_COLUMNS: tuple[str, ...] = (
    "run_id", "client_id", "program_code", "tax_year", "fiscal_year_begin",
    "fiscal_year_end", "step1_assumption_set_id", "onezero_assumption_set_id",
    "rule_pack_version", "code_commit", "calculation_id", "run_started_at",
    "run_completed_at", "run_status", "superseded_by_run_id", "triggered_by",
)


def _value(column: str, value: Any) -> Any:
    """One warehouse value as JSON carries it."""
    if value is None:
        return None
    if column in _MONEY_COLUMNS:
        return str(value)
    if column in _BOOL_COLUMNS:
        return bool(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [description[0] for description in cursor.description]
    return [
        {column: _value(column, cell) for column, cell in zip(columns, row)}
        for row in cursor.fetchall()
    ]


# --------------------------------------------------------------- statements
#
# Every read below is built here rather than inline, because each one is issued
# two ways: on its own, and inside a batch. A page was costing eight sequential
# round trips at a ~125ms floor each — the queries themselves are near the
# engine's floor, so the cost was the count of trips, not the work.
#
# If a statement existed twice it would eventually differ, and a batched read
# quietly returning different rows from the individual one is the kind of fault
# that reaches a filed return. One definition, two callers.

Statement = tuple[str, list[Any]]

#: SQLSTATEs meaning "the link is gone", as opposed to "your SQL is wrong".
#: Only these are retried; a syntax error retried is a syntax error twice.
_CONNECTION_LOST_STATES = frozenset({"08S01", "08003", "08001", "01000", "HYT00"})


def _stmt_latest_run(client_id: int) -> Statement:
    """The live run for a CLIENT. Deliberately not narrowed by tax year.

    A run writes every year the payroll covers, so `run_manifest.tax_year` is
    the year the run was COMMANDED for, not the set of years it produced.
    Filtering on it made a client's other years read as `not_calculated` while
    their rows sat in Gold. Supersession already answers "which run is current",
    and it answers it per client.

    The year belongs on the `tcc_gold` read instead, where `tax_year` and
    `is_current` already live.
    """
    return (
        f"SELECT TOP 1 {', '.join(_MANIFEST_COLUMNS)} FROM {OPS_SCHEMA}.run_manifest "
        f"WHERE client_id = ? AND run_status = 'success' "
        f"AND superseded_by_run_id IS NULL AND run_completed_at IS NOT NULL "
        f"ORDER BY run_started_at DESC",
        [client_id],
    )


def _stmt_run_in_flight(client_id: int) -> Statement:
    # The age guard is what stops a process that died mid-run from advertising
    # itself as in flight forever. The reaper closes those rows durably, but a
    # run can strand at any moment and the next read must not repeat the lie.
    return (
        f"SELECT TOP 1 run_id, run_started_at, triggered_by, tax_year "
        f"FROM {OPS_SCHEMA}.run_manifest "
        f"WHERE client_id = ? AND run_completed_at IS NULL "
        f"AND run_status = 'running' "
        f"AND run_started_at >= DATEADD(minute, ?, SYSUTCDATETIME()) "
        f"ORDER BY run_started_at DESC",
        [client_id, -abs(STRANDED_RUN_MINUTES)],
    )


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


def _stmt_drill_verdicts(client_id: int, tax_year: int, run_id: str, token: str) -> Statement:
    """Both methods' averages for one employee, by the handle the run minted.

    `record_token` is a STORED column, so this is a lookup. The drill used to
    resolve a token by re-minting one for every employee in the client-year and
    matching — 10,236 hashes for the reference client, on top of two full engine
    replays, per click.
    """
    return (
        f"SELECT method, employee_id, weeks_worked, total_hours, total_wages, "
        f"  avg_weekly_hours, avg_weekly_wages, eligible, weight, days, "
        f"  first_start, last_end "
        f"FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ? AND tax_year = ? AND run_id = ? AND record_token = ?",
        [client_id, tax_year, run_id, token],
    )


def _stmt_drill_segments(client_id: int, tax_year: int, run_id: str, token: str) -> Statement:
    months = ", ".join(f"month_{index:02d}" for index in range(1, 13))
    return (
        f"SELECT method, worksite_id, entity_fein, first_pps, last_ppe, weight, {months} "
        f"FROM {GOLD_SCHEMA}.onezero_matrix "
        f"WHERE client_id = ? AND tax_year = ? AND run_id = ? AND record_token = ? "
        f"ORDER BY method, worksite_id, first_pps",
        [client_id, tax_year, run_id, token],
    )


def _stmt_drill_periods(client_id: int, tax_year: int, run_id: str, token: str) -> Statement:
    return (
        f"SELECT worksite_id, entity_fein, job_title, pay_period_start, pay_period_end, "
        f"  pay_date, pay_frequency_code, hours, wages, pay_code, selection_decision "
        f"FROM {GOLD_SCHEMA}.employee_period_fact "
        f"WHERE client_id = ? AND tax_year = ? AND run_id = ? AND record_token = ? "
        f"ORDER BY pay_period_end",
        [client_id, tax_year, run_id, token],
    )


def _stmt_cohort_periods(client_id: int, tax_year: int, run_id: str, tokens: list[str]) -> Statement:
    marks = ", ".join("?" for _ in tokens)
    return (
        f"SELECT record_token, worksite_id, pay_period_start, pay_period_end, pay_date, hours, wages "
        f"FROM {GOLD_SCHEMA}.employee_period_fact "
        f"WHERE client_id = ? AND tax_year = ? AND run_id = ? AND record_token IN ({marks}) "
        f"ORDER BY record_token, pay_period_end",
        [client_id, tax_year, run_id, *tokens],
    )


def _stmt_at_risk(
    client_id: int, tax_year: int, method: str, run_id: str,
    min_hours: float, min_wages: float, band: float,
) -> Statement:
    """Employees who QUALIFIED but sit barely above a floor.

    The mirror of the near-miss cohort, and a different question: those are
    people who could come in, these are jobs already counted toward the credit
    that could fall out of it. A client asking "which of my net-new jobs might
    I lose" is asking about this set.

    Banded on EITHER floor, because clearing the credit needs both — somebody
    at twice the hours floor and one dollar over the wage floor is fragile, and
    a filter on hours alone would call them safe.
    """
    hours_ceiling = float(min_hours) * (1.0 + band)
    wages_ceiling = float(min_wages) * (1.0 + band)
    return (
        f"SELECT employee_id, record_token, weeks_worked, total_hours, total_wages, "
        f"avg_weekly_hours, avg_weekly_wages, weight "
        f"FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ? "
        f"AND eligible = 1 AND avg_weekly_hours IS NOT NULL "
        f"AND (avg_weekly_hours < ? OR avg_weekly_wages < ?) "
        f"ORDER BY avg_weekly_hours",
        [client_id, tax_year, method, run_id, hours_ceiling, wages_ceiling],
    )


def _stmt_at_risk_counts(
    client_id: int, tax_year: int, method: str, run_id: str,
) -> Statement:
    """How many qualified at all — the denominator the band is a fraction of."""
    return (
        f"SELECT COUNT(*) AS evaluated, "
        f"  SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS eligible_count "
        f"FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ? "
        f"AND avg_weekly_hours IS NOT NULL",
        [client_id, tax_year, method, run_id],
    )


def _stmt_proximity_counts(
    client_id: int, tax_year: int, method: str, run_id: str,
    min_hours: float, min_wages: float,
) -> Statement:
    """Population counts over EVERY averaged employee, not just the near ones.

    The cohort rows are prefiltered to those that could reach the band; these
    counts must not be, because "24 of 9,541 considered" is the sentence the
    screen makes and the denominator is the honest half of it.

    Failure modes are classified by the floors and counted over the RECORDED
    ineligible, which is exactly what `near_miss_cohort` does in Python.

    The count aliases must NOT collide with `_BOOL_COLUMNS`. Summing into an
    alias named `eligible` came back as `True`, and `int(True)` is 1 — so 539
    eligible employees reported as one. Same trap as a money aggregate aliased
    to a name `_MONEY_COLUMNS` does not carry.
    """
    return (
        f"SELECT COUNT(*) AS evaluated, "
        f"  SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS eligible_count, "
        f"  SUM(CASE WHEN eligible = 0 THEN 1 ELSE 0 END) AS ineligible_count, "
        f"  SUM(CASE WHEN eligible = 0 AND avg_weekly_hours <  ? "
        f"           AND avg_weekly_wages >= ? THEN 1 ELSE 0 END) AS hours_only, "
        f"  SUM(CASE WHEN eligible = 0 AND avg_weekly_hours >= ? "
        f"           AND avg_weekly_wages <  ? THEN 1 ELSE 0 END) AS wages_only, "
        f"  SUM(CASE WHEN eligible = 0 AND avg_weekly_hours <  ? "
        f"           AND avg_weekly_wages <  ? THEN 1 ELSE 0 END) AS both "
        f"FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ? "
        f"AND avg_weekly_hours IS NOT NULL",
        [
            float(min_hours), float(min_wages),
            float(min_hours), float(min_wages),
            float(min_hours), float(min_wages),
            client_id, tax_year, method, run_id,
        ],
    )


def _stmt_proximity_candidates(
    client_id: int, tax_year: int, method: str, run_id: str,
    reachable_at_or_above: float,
) -> Statement:
    """Every employee who could still reach the widest band on offer.

    `avg_weekly_hours IS NOT NULL` reproduces `OneZeroResult.all_averages`. The
    156 reference employees with hours and wages but no qualifying pay period
    are stored with NULL averages and are genuinely unassessable here — they
    have no weekly rate to move, so offering them a lever would be arithmetic
    from nothing.

    The hours bound is a NECESSARY condition, not an approximation. The lever is
    `max(hours_gap, wages_gap / rate)`, so it is never smaller than `hours_gap`;
    anyone within `B` hours of qualifying therefore has `avg_weekly_hours >=
    min_hours - B` whatever they earn. Fetching the other 9,377 rows to discover
    they are far away cost 19 of the reference client's 21 seconds.
    """
    return (
        f"SELECT employee_id, record_token, weeks_worked, total_hours, total_wages, "
        f"avg_weekly_hours, avg_weekly_wages, eligible, weight "
        f"FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ? AND tax_year = ? AND method = ? AND run_id = ? "
        f"AND avg_weekly_hours IS NOT NULL AND avg_weekly_hours >= ?",
        [client_id, tax_year, method, run_id, float(reachable_at_or_above)],
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


#: The eligibility population, pivoted so one row carries BOTH methods.
#:
#: `employee_eligibility` is one row per employee per method, and the screen
#: asks a question about the employee — did Min-Max and Pay Period agree about
#: this person. Pivoting in SQL means the page never holds two rows it has to
#: match up, and never holds 10,236 of them to count four buckets.
#:
#: `total_hours` / `total_wages` are per employee, not per method, so MAX over
#: the group is the value itself rather than a choice between two.
_ELIGIBILITY_PIVOT = f"""
SELECT employee_id,
       MAX(record_token) AS record_token,
       MAX(CASE WHEN method = 'min_max' THEN weeks_worked END) AS mm_weeks,
       MAX(CASE WHEN method = 'min_max' THEN avg_weekly_hours END) AS mm_hours,
       MAX(CASE WHEN method = 'min_max' THEN avg_weekly_wages END) AS mm_wages,
       MAX(CASE WHEN method = 'min_max' THEN CAST(eligible AS int) END) AS mm_eligible,
       MAX(CASE WHEN method = 'pay_period' THEN weeks_worked END) AS pp_weeks,
       MAX(CASE WHEN method = 'pay_period' THEN avg_weekly_hours END) AS pp_hours,
       MAX(CASE WHEN method = 'pay_period' THEN avg_weekly_wages END) AS pp_wages,
       MAX(CASE WHEN method = 'pay_period' THEN CAST(eligible AS int) END) AS pp_eligible,
       MAX(total_hours) AS total_hours,
       MAX(total_wages) AS total_wages
FROM {GOLD_SCHEMA}.employee_eligibility
WHERE client_id = ? AND tax_year = ? AND run_id = ?
GROUP BY employee_id
"""

#: Reads exactly like `_status_of` did in Python, and must keep doing so.
_ELIGIBILITY_STATUS = (
    "CASE WHEN mm_eligible = 1 AND pp_eligible = 1 THEN 'both' "
    "WHEN mm_eligible = 1 THEN 'min_max_only' "
    "WHEN pp_eligible = 1 THEN 'pay_period_only' "
    "ELSE 'neither' END"
)

#: Within `band` of a floor, on the FAILING side of it. The floors arrive as
#: parameters from the year pack: a literal here would bake Georgia's into
#: every jurisdiction, which is the same rule the near-threshold band follows.
_ELIGIBILITY_NEAR = (
    "CASE WHEN ("
    "  (mm_hours IS NOT NULL AND mm_hours < ? AND mm_hours >= ?) OR"
    "  (mm_wages IS NOT NULL AND mm_wages < ? AND mm_wages >= ?) OR"
    "  (pp_hours IS NOT NULL AND pp_hours < ? AND pp_hours >= ?) OR"
    "  (pp_wages IS NOT NULL AND pp_wages < ? AND pp_wages >= ?)"
    ") THEN 1 ELSE 0 END"
)


#: Rows where the RECORDED verdict and today's floors disagree.
#:
#: `eligible` is read from the run; `passed_hours` / `passed_wages` and the
#: near-floor band are drawn from the floors resolved NOW, and they agree only
#: while the rule pack has not been re-authored since. `rule_pack_version` on
#: the manifest cannot detect that — it stores the pack's PATH, and re-authoring
#: a materialised year pack changes its contents but not its filename.
#:
#: Absent a part-time band, `eligible` must equal "cleared both floors", so any
#: row where it does not means the ruler moved. Counted here because the
#: alternative is fetching the population to tally it.
_ELIGIBILITY_DRIFT = (
    "CASE WHEN"
    "  (mm_hours IS NOT NULL AND mm_eligible <> ("
    "     CASE WHEN mm_hours >= ? AND mm_wages >= ? THEN 1 ELSE 0 END)) OR"
    "  (pp_hours IS NOT NULL AND pp_eligible <> ("
    "     CASE WHEN pp_hours >= ? AND pp_wages >= ? THEN 1 ELSE 0 END))"
    " THEN 1 ELSE 0 END"
)


def _near_params(min_hours: float, min_wages: float, band: float) -> list[Any]:
    hours_floor, wages_floor = float(min_hours), float(min_wages)
    near_hours = hours_floor * (1 - band)
    near_wages = wages_floor * (1 - band)
    return [
        hours_floor, near_hours, wages_floor, near_wages,
        hours_floor, near_hours, wages_floor, near_wages,
    ]


def _stmt_eligibility_summary(
    client_id: int, tax_year: int, run_id: str,
    min_hours: float, min_wages: float, band: float,
) -> Statement:
    """Every count the page states, in one statement over the whole population.

    Counted in SQL rather than by fetching 10,236 rows and tallying them: the
    figures here are the certified ones, and the cost of getting them must not
    scale with the client.
    """
    return (
        f"WITH pivoted AS ({_ELIGIBILITY_PIVOT}), "
        f"classified AS (SELECT {_ELIGIBILITY_STATUS} AS status, "
        f"  {_ELIGIBILITY_NEAR} AS near_floor, "
        f"  {_ELIGIBILITY_DRIFT} AS verdict_drift, "
        f"  mm_eligible, pp_eligible FROM pivoted) "
        f"SELECT COUNT(*) AS employees_evaluated, "
        f"  SUM(CASE WHEN mm_eligible = 1 THEN 1 ELSE 0 END) AS min_max_eligible, "
        f"  SUM(CASE WHEN pp_eligible = 1 THEN 1 ELSE 0 END) AS pay_period_eligible, "
        f"  SUM(CASE WHEN mm_eligible = 1 OR pp_eligible = 1 THEN 1 ELSE 0 END) AS eligible_either, "
        f"  SUM(near_floor) AS near_floor, "
        f"  SUM(CASE WHEN status = 'both' THEN 1 ELSE 0 END) AS eligible_both, "
        f"  SUM(CASE WHEN status = 'min_max_only' THEN 1 ELSE 0 END) AS min_max_only, "
        f"  SUM(CASE WHEN status = 'pay_period_only' THEN 1 ELSE 0 END) AS pay_period_only, "
        f"  SUM(CASE WHEN status = 'neither' THEN 1 ELSE 0 END) AS neither, "
        f"  SUM(verdict_drift) AS verdict_disagreements "
        f"FROM classified",
        [
            client_id, tax_year, run_id,
            *_near_params(min_hours, min_wages, band),
            float(min_hours), float(min_wages), float(min_hours), float(min_wages),
        ],
    )


def _eligibility_filter(
    status: str, near_floor: bool, q: str
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if status and status != "all":
        clauses.append("status = ?")
        values.append(status)
    if near_floor:
        clauses.append("near_floor = 1")
    if q and q.strip():
        escaped = q.strip().replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
        clauses.append("LOWER(employee_id) LIKE ?")
        values.append(f"%{escaped.lower()}%")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", values


#: Sortable columns of the eligibility page, mapped to the pivot's own names.
#: A whitelist: the key arrives from a query string (29 Sep, every table sorts).
ELIGIBILITY_SORTS = {
    "employee_id": "employee_id",
    "status": "status",
    "near_floor": "near_floor",
    "total_hours": "total_hours",
    "total_wages": "total_wages",
    "mm_weeks": "mm_weeks",
    "mm_hours": "mm_hours",
    "pp_weeks": "pp_weeks",
    "pp_hours": "pp_hours",
}


def _stmt_eligibility_page(
    client_id: int, tax_year: int, run_id: str,
    min_hours: float, min_wages: float, band: float,
    status: str, near_floor: bool, q: str, limit: int, offset: int,
    sort: str = "employee_id", order: str = "asc",
) -> Statement:
    """One page of the population, filtered and ordered in SQL.

    Ordered BEFORE the page is cut, so the first page of "by total hours" is the
    top of all 10,236 and not the top of the fifty that happened to come back.
    """
    where, filter_values = _eligibility_filter(status, near_floor, q)
    column = ELIGIBILITY_SORTS.get(sort, "employee_id")
    direction = "DESC" if str(order).lower() == "desc" else "ASC"
    order_by = (
        f"ORDER BY {column} {direction}"
        + ("" if column == "employee_id" else ", employee_id ASC")
    )
    return (
        f"WITH pivoted AS ({_ELIGIBILITY_PIVOT}), "
        f"classified AS (SELECT *, {_ELIGIBILITY_STATUS} AS status, "
        f"  {_ELIGIBILITY_NEAR} AS near_floor FROM pivoted) "
        f"SELECT * FROM classified{where} "
        f"{order_by} "
        f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        [
            client_id, tax_year, run_id, *_near_params(min_hours, min_wages, band),
            *filter_values, int(offset), int(limit),
        ],
    )


def _stmt_eligibility_matching(
    client_id: int, tax_year: int, run_id: str,
    min_hours: float, min_wages: float, band: float,
    status: str, near_floor: bool, q: str,
) -> Statement:
    """How many rows the filter matched — the denominator for paging.

    Separate from the summary because that one must NEVER move with a filter:
    the certified counts are a statement about the client, not about what the
    reader narrowed to.
    """
    where, filter_values = _eligibility_filter(status, near_floor, q)
    return (
        f"WITH pivoted AS ({_ELIGIBILITY_PIVOT}), "
        f"classified AS (SELECT *, {_ELIGIBILITY_STATUS} AS status, "
        f"  {_ELIGIBILITY_NEAR} AS near_floor FROM pivoted) "
        f"SELECT COUNT(*) AS total FROM classified{where}",
        [
            client_id, tax_year, run_id, *_near_params(min_hours, min_wages, band),
            *filter_values,
        ],
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


class GoldReader:
    """Reads one client's figures from `tcc_gold`, and nothing else."""

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    @property
    def connection(self) -> FabricWarehouseConnection:
        return self._connection

    def scope(self):
        """Run a page's reads on ONE connection.

        Every method below opens its own, which is right for a single query and
        wrong for a page: the unit drill made six. Wrapping the endpoint body in
        this collapses them without touching any of the methods.
        """
        return self._connection.scope()

    def _retrying(self, work):
        """Run a read, reopening once if the connection had died while parked.

        Connections are reused between requests, so the first statement of a
        page can land on a link Fabric closed server-side. Every caller here is
        a SELECT, so re-running it is safe; this deliberately does not wrap
        writes, where a retry is a second attempt at a state change.
        """
        import pyodbc

        try:
            return work()
        except pyodbc.Error as exc:
            state = exc.args[0] if exc.args else ""
            if state not in _CONNECTION_LOST_STATES:
                raise
            self._connection.invalidate()
            return work()

    def _many(self, statement: Statement) -> list[dict[str, Any]]:
        sql, values = statement

        def work() -> list[dict[str, Any]]:
            with self._connection.connect() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(sql, values)
                    return _rows(cursor)
                finally:
                    # A pooled link must go back with no statement active, or
                    # the next borrower gets "Connection is busy with results
                    # for another command" — intermittently, on GC timing.
                    cursor.close()

        return self._retrying(work)

    def _one(self, statement: Statement) -> dict[str, Any] | None:
        found = self._many(statement)
        return found[0] if found else None

    def _batch(self, statements: list[Statement]) -> list[list[dict[str, Any]]]:
        """Several statements, ONE round trip.

        Each query here is already near the engine's floor — `SELECT 1` costs
        125ms against this warehouse, and a real read ~300ms — so issuing eight
        of them serially spends the round trip eight times. Batched, the same
        eight cost one. Measured 1,127ms -> 403ms on the units page.

        Result sets come back in statement order and are walked with
        `nextset()`. A statement returning no rows still returns a set, so the
        positional mapping holds and the caller can unpack by position.
        """
        sql = ";\n".join(s for s, _ in statements)
        values = [v for _, vs in statements for v in vs]

        def work() -> list[list[dict[str, Any]]]:
            out: list[list[dict[str, Any]]] = []
            with self._connection.connect() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(sql, values)
                    for index in range(len(statements)):
                        out.append(_rows(cursor))
                        if index < len(statements) - 1 and not cursor.nextset():
                            break
                finally:
                    cursor.close()
            return out

        return self._retrying(work)

    # ------------------------------------------------------------ run identity

    def latest_run(self, client_id: int) -> dict[str, Any] | None:
        """The live run for a client, or None when it has never been calculated.

        Live means completed successfully and not yet superseded. `None` is the
        `not_calculated` state and callers must not render it as a zero.

        Takes no tax year: a run is current for a client, and the year selects
        ROWS rather than runs. See `_stmt_latest_run`.
        """
        return self._one(_stmt_latest_run(client_id))

    def run_in_flight(self, client_id: int) -> dict[str, Any] | None:
        """A run that has started and not finished, or None.

        `run_completed_at IS NULL` is the marker: the manifest is written at the
        START of a run and stamped on completion. A row still sitting here long
        after it began is a run that died without saying so, which is worth
        showing rather than hiding.
        """
        return self._one(_stmt_run_in_flight(client_id))

    # ----------------------------------------------------------------- reads

    def _unit_page_whole(
        self, client_id: int, method: str, program_code: str | None, limit: int, offset: int
    ) -> dict[str, Any]:
        """The grid in ONE round trip, for the shape the screen actually asks for.

        The UI never sends a year — `fetchClientUnits` omits it — because the
        grid draws every year a location has. That makes the item rows and the
        per-unit money the same row set, so the money can be a window over the
        rows already being read instead of two more scans of the same table.

        Four statements, one trip: the run, the run in flight, the grid, the
        credit stream. The month summary is joined on `m.run_id` rather than on
        a resolved run id, so nothing here waits for the first result.
        """
        run_rows, in_flight_rows, grid, credits = self._batch([
            _stmt_latest_run(client_id),
            _stmt_run_in_flight(client_id),
            _stmt_unit_grid(client_id, method, program_code, limit, offset),
            _stmt_credit_grid(client_id, method, program_code),
        ])
        run = run_rows[0] if run_rows else None
        in_flight = in_flight_rows[0] if in_flight_rows else None
        if run is None:
            return {"run": None, "in_flight": in_flight, "items": [], "total": 0,
                    "months": [], "installments": [], "unit_totals": []}

        items: list[dict[str, Any]] = []
        months: list[dict[str, Any]] = []
        totals: dict[str, dict[str, Any]] = {}
        for row in grid:
            worksite = row["worksite_id"]
            items.append({
                **{column: row[column] for column in UNIT_YEAR_MASTER_COLUMNS},
                "months_with_headcount": row["months_with_headcount"],
                "unreachable_months": row["unreachable_months"],
            })
            # A unit-year with no summary row joined is not a month of zeroes;
            # it is a month grain that does not exist, and the grid draws those
            # differently.
            if row["month_total"] is not None or any(
                row[column] is not None for column in _MONTH_COLUMNS
            ):
                months.append({
                    "client_id": row["client_id"],
                    "tax_year": row["tax_year"],
                    "method": row["method"],
                    "run_id": row["run_id"],
                    "worksite_id": worksite,
                    **{column: row[column] for column in _MONTH_COLUMNS},
                    "total": row["month_total"],
                    "average_headcount": row["month_average_headcount"],
                    "months_with_headcount": row["months_with_headcount"],
                    "unreachable_months": row["unreachable_months"],
                })
            if worksite not in totals:
                totals[worksite] = {
                    "worksite_id": worksite,
                    "total_annual_credit_usd": row["total_annual_credit_usd"],
                    "final_high_water_mark": row["final_high_water_mark"],
                    "total_tranche_lifetime_usd": None,
                }

        installments = []
        for row in credits:
            lifetime = row.pop("total_tranche_lifetime_usd")
            installments.append(row)
            if row["worksite_id"] in totals:
                totals[row["worksite_id"]]["total_tranche_lifetime_usd"] = lifetime

        return {
            "run": run,
            "in_flight": in_flight,
            "items": items,
            "total": int(grid[0]["total_rows"]) if grid else 0,
            "months": months,
            "installments": installments,
            "unit_totals": [totals[key] for key in sorted(totals)],
        }

    def unit_page(
        self,
        client_id: int,
        *,
        method: str,
        tax_year: int | None = None,
        program_code: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Everything the units grid renders, in TWO round trips.

        The same six reads the endpoint used to make one at a time. Each is
        already a plain SELECT off pre-computed Gold and runs near the engine's
        floor; the page cost was the eight trips, not the work — 2,334ms of
        which roughly 1,000ms was floor.

        It is two trips and not one because `month_summaries` is keyed by the
        run id that the first trip resolves. Folding `latest_run` into the
        second batch as a subquery would remove the dependency, and also remove
        the early exit: a client with no run must not pay for six reads whose
        answer is already known to be empty.
        """
        if tax_year is None:
            return self._unit_page_whole(client_id, method, program_code, limit, offset)

        run_rows, in_flight_rows = self._batch([
            _stmt_latest_run(client_id),
            _stmt_run_in_flight(client_id),
        ])
        run = run_rows[0] if run_rows else None
        in_flight = in_flight_rows[0] if in_flight_rows else None
        if run is None:
            return {"run": None, "in_flight": in_flight, "items": [], "total": 0,
                    "months": [], "installments": [], "unit_totals": []}

        counted, items, months, installments, totals, lifetime_rows = self._batch([
            _stmt_unit_years_count(client_id, method, tax_year, program_code),
            _stmt_unit_years(client_id, method, tax_year, program_code, limit, offset),
            _stmt_month_summaries(client_id, method, run["run_id"], tax_year),
            _stmt_credit_columns(client_id, method, program_code),
            _stmt_unit_totals(client_id, method, program_code),
            _stmt_unit_lifetime(client_id, method, program_code),
        ])
        lifetime = {r["worksite_id"]: r["total_tranche_lifetime_usd"] for r in lifetime_rows}
        for row in totals:
            row["total_tranche_lifetime_usd"] = lifetime.get(row["worksite_id"])

        return {
            "run": run,
            "in_flight": in_flight,
            "items": items,
            "total": int(counted[0]["total"]) if counted else 0,
            "months": months,
            "installments": installments,
            "unit_totals": totals,
        }

    def unit_years(
        self,
        client_id: int,
        *,
        method: str,
        tax_year: int | None = None,
        program_code: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Unit-year rows for the live run, with the month-grain columns joined.

        Every `unit_year_master` column is returned, including `per_job_usd` and
        `tranche_years` — without the rate, `annual_credit_usd` cannot be checked
        against `eligible_jobs` from the row itself, which is the whole point of
        the credit layer living in Gold.
        """
        counted, items = self._batch([
            _stmt_unit_years_count(client_id, method, tax_year, program_code),
            _stmt_unit_years(client_id, method, tax_year, program_code, limit, offset),
        ])
        return items, int(counted[0]["total"]) if counted else 0

    def unit(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str
    ) -> dict[str, Any] | None:
        """One unit-year row, or None when the run holds no such unit."""
        return self._one(_stmt_unit(client_id, worksite_id, tax_year, method))

    def unit_months(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str, run_id: str
    ) -> dict[str, Any] | None:
        return self._one(_stmt_unit_months(client_id, worksite_id, tax_year, method, run_id))

    def month_summaries(
        self, client_id: int, *, method: str, run_id: str, tax_year: int | None = None
    ) -> list[dict[str, Any]]:
        """Every unit's monthly row for the run — the grid's twelve columns."""
        return self._many(_stmt_month_summaries(client_id, method, run_id, tax_year))

    def installments(
        self, client_id: int, *, method: str, program_code: str | None = None
    ) -> list[dict[str, Any]]:
        """The credit tranches: creation year x claimable year, per unit.

        A job created once pays out across its window, so this is a different
        grain from `unit_year_master` and cannot be derived from it. Without it
        the grid has no YR1..YRn columns to show.
        """
        statement = (
            f"SELECT * FROM {GOLD_SCHEMA}.unit_credit_installment "
            f"WHERE client_id = ? AND method = ? AND is_current = 1"
        )
        values: list[Any] = [client_id, method]
        if program_code:
            statement += " AND program_code = ?"
            values.append(program_code)
        statement += " ORDER BY worksite_id, creation_year, tax_year"

        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, values)
                return _rows(cursor)
            finally:
                cursor.close()

    def credit_columns(
        self, client_id: int, *, method: str, program_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Claimable dollars per unit per YEAR, summed across creation years.

        Several tranches can pay out in the same year, so the grid's YR1..YRn
        column is a SUM over `unit_credit_installment`. It is done here because
        adding money in a browser means adding it as a float.

        `projected` is true if ANY contributing installment is a forecast — a
        column mixing observed and assumed dollars must not read as observed.
        """
        return self._many(_stmt_credit_columns(client_id, method, program_code))

    def unit_totals(
        self, client_id: int, *, method: str, program_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Per-unit money, summed IN SQL rather than on screen.

        The roll-up strip is counts and totals, never a re-derivation of dollars
        — so the sum happens once, here, over the same rows the grid renders.
        """
        totals, lifetime_rows = self._batch([
            _stmt_unit_totals(client_id, method, program_code),
            _stmt_unit_lifetime(client_id, method, program_code),
        ])
        lifetime = {r["worksite_id"]: r["total_tranche_lifetime_usd"] for r in lifetime_rows}
        for row in totals:
            row["total_tranche_lifetime_usd"] = lifetime.get(row["worksite_id"])
        return totals

    def unit_employees(
        self,
        client_id: int,
        worksite_id: str,
        *,
        tax_year: int,
        method: str,
        run_id: str,
        month: int | None = None,
    ) -> list[dict[str, Any]]:
        """Employees allocated to one unit, optionally NARROWED to one month.

        `month` filters, it does not merely annotate. A drawer headed "Month 5"
        that lists everyone at the unit and counts them all is telling the
        operator the wrong number: at Cascade's GA_GA-001 that is 29 people
        where the statutory answer is 25.

        The join to `employee_eligibility` carries the hours and wages the
        matrix does not hold, so a page can sort on effort without a second
        round trip. It is 1:1 on the full key and does not fan out.
        """
        return self._many(
            _stmt_unit_employees(client_id, worksite_id, tax_year, method, run_id, month)
        )

    def unit_near_threshold(
        self,
        client_id: int,
        worksite_id: str,
        *,
        tax_year: int,
        method: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        """Employees at this unit who did NOT qualify — the actionable cohort.

        `onezero_matrix` holds only the qualified, so no join to it can surface
        a near miss: the cusp count comes back zero at every unit on every
        client. The people one shift short are in `employee_eligibility`, which
        has no worksite; `employee_period_fact` places them.

        DISTINCT because period_fact is one row per pay period. Nobody in the
        reference data spans two worksites, so this does not fan out — but the
        DISTINCT is what makes that a property of the query rather than a
        property of the current data.
        """
        return self._many(
            _stmt_unit_near_threshold(client_id, worksite_id, tax_year, method, run_id)
        )

    def headcount_series(
        self, client_id: int, *, tax_year: int, method: str
    ) -> dict[str, Any]:
        """The monthly headcount series and the annual average, READ.

        The in-year forecast replayed the whole payroll TWICE to get these —
        once for the year being projected and once for the prior-year base. Both
        were already written by the run. The forecast itself still computes,
        because projecting to an arbitrary as-of date is a genuine derivation
        rather than a re-derivation of a certified figure.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "months": [], "annual_average": None, "month_ends": []}

        month_rows, summary_rows = self._batch([
            _stmt_month_totals(client_id, tax_year, method, run["run_id"]),
            _stmt_method_summary(client_id, tax_year, method, run["run_id"]),
        ])
        row = month_rows[0] if month_rows else {}
        months = [float(row.get(f"month_{index:02d}") or 0.0) for index in range(1, 13)]
        summary = summary_rows[0] if summary_rows else None
        # The run's REAL month ends, not a calendar assumption. A client whose
        # fiscal year opens in August has no August-to-December meaning, and
        # counting elapsed months off 1 January would misplace every one.
        month_ends: list[str] = []
        if summary and summary.get("month_ends"):
            try:
                month_ends = list(json.loads(str(summary["month_ends"])))
            except (ValueError, TypeError):
                month_ends = []
        return {
            "run": run,
            "months": months,
            "month_ends": month_ends,
            # 0-based positions no pay period reaches. For an open year the
            # trailing ones are months that have not happened yet.
            "unreachable_months": [
                int(part) for part in str(row.get("unreachable_months") or "").split(",")
                if part.strip().isdigit()
            ],
            "annual_average": (
                float(summary["annual_average"]) if summary and summary.get("annual_average") is not None
                else None
            ),
        }

    def client_year_series(
        self, client_id: int, *, method: str = "pay_period"
    ) -> dict[str, Any]:
        """Every year the run holds for a client, and what each concluded.

        The cross-year view: annual average, eligible count and credit per tax
        year, plus which year the base was set. "Have they been eligible since
        their base year" is a question about a SERIES, and answering it from a
        single-year read is how a chat ends up describing one year as though it
        were the whole history.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "years": []}

        summary_rows, credit_rows = self._batch([
            _stmt_client_year_series(client_id, method, run["run_id"]),
            _stmt_client_year_credit(client_id, method),
        ])
        credit_by_year = {int(r["tax_year"]): r for r in credit_rows}

        years: list[dict[str, Any]] = []
        for row in summary_rows:
            year = int(row["tax_year"])
            credit = credit_by_year.get(year, {})
            years.append({
                "tax_year": year,
                "annual_average": float(row["annual_average"] or 0),
                "eligible_employees": int(row["eligible_employees"] or 0),
                "employees_evaluated": int(row["employees_evaluated"] or 0),
                "annual_credit_usd": (
                    str(credit["annual_credit_usd"])
                    if credit.get("annual_credit_usd") is not None else None
                ),
                "is_base_year": bool(credit.get("has_base_year")),
                "qualified_units": (
                    int(credit["qualified_units"])
                    if credit.get("qualified_units") is not None else 0
                ),
                "units": int(credit["units"]) if credit.get("units") is not None else 0,
            })
        return {"run": run, "years": years, "method": method}

    def at_risk(
        self,
        client_id: int,
        *,
        tax_year: int,
        method: str,
        min_weekly_hours: float,
        min_weekly_wages: float,
        band: float = 0.10,
    ) -> dict[str, Any]:
        """Qualified employees sitting barely above a floor, READ.

        "Which of the net-new jobs counted toward the credit might fall out of
        it" is a question about the people already INSIDE, and no near-miss
        read can answer it: that cohort is everybody outside.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "rows": [], "counts": None}

        counts_rows, rows = self._batch([
            _stmt_at_risk_counts(client_id, tax_year, method, run["run_id"]),
            _stmt_at_risk(
                client_id, tax_year, method, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
            ),
        ])
        return {
            "run": run,
            "rows": rows,
            "counts": counts_rows[0] if counts_rows else None,
        }

    def proximity_candidates(
        self,
        client_id: int,
        *,
        tax_year: int,
        method: str,
        min_weekly_hours: float,
        min_weekly_wages: float,
        widest_band_hours: float,
    ) -> dict[str, Any]:
        """Everyone who could still reach the band, and the counts they sit in.

        This used to replay `run_min_max_method` over the whole client payroll
        on every ClientPage load — 61 seconds for the reference client, on a
        screen that ran two more replays behind the forecast. Every field the
        assessment needs was already written by the run.

        NOT `proximity_population`: `rows` is bounded to the reachable band and
        is emphatically not the population. `counts` is, and the two are
        separate statements so that a denominator can never be quietly taken
        over the filtered set.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "rows": [], "counts": None}

        counts_rows, rows = self._batch([
            _stmt_proximity_counts(
                client_id, tax_year, method, run["run_id"],
                min_weekly_hours, min_weekly_wages,
            ),
            _stmt_proximity_candidates(
                client_id, tax_year, method, run["run_id"],
                float(min_weekly_hours) - float(widest_band_hours),
            ),
        ])
        return {
            "run": run,
            "rows": rows,
            "counts": counts_rows[0] if counts_rows else None,
        }

    def cohort_periods(
        self, client_id: int, *, tax_year: int, run_id: str, tokens: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Pay periods for a handful of employees, grouped by record token.

        The near-the-line cohort is ten rows. One statement for all of them;
        the rest-of-year reading needs each one's periods up to the checkpoint.
        """
        wanted = [t for t in dict.fromkeys(tokens) if t]
        if not wanted:
            return {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self._many(_stmt_cohort_periods(client_id, tax_year, run_id, wanted)):
            grouped.setdefault(str(row["record_token"]), []).append(row)
        return grouped

    def onezero_matrix(
        self, client_id: int, *, tax_year: int, method: str
    ) -> dict[str, Any]:
        """The One/Zero allocation for one client-year-method, READ.

        The screen states four things that belong to the run rather than to any
        row — annual average, eligible count, matrix rows and CONTESTED months.
        `run_method_summary` holds them because nothing else could: the matrix
        is deduped before it is written, so a contest leaves no trace in the
        rows it produced.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "summary": None, "matrix": [], "units": []}

        summary_rows, matrix_rows, unit_rows = self._batch([
            _stmt_method_summary(client_id, tax_year, method, run["run_id"]),
            _stmt_onezero_matrix(client_id, tax_year, method, run["run_id"]),
            _stmt_unit_fein_summary(client_id, tax_year, method, run["run_id"]),
        ])
        summary = summary_rows[0] if summary_rows else None
        if summary is None:
            return {"run": run, "summary": None, "matrix": [], "units": []}
        return {
            "run": run,
            "summary": summary,
            "matrix": matrix_rows,
            "units": unit_rows,
        }

    def eligibility_population(
        self,
        client_id: int,
        *,
        tax_year: int,
        min_weekly_hours: float,
        min_weekly_wages: float,
        band: float = 0.05,
        status: str = "all",
        near_floor: bool = False,
        q: str = "",
        limit: int = 50,
        offset: int = 0,
        sort: str = "employee_id",
        order: str = "asc",
    ) -> dict[str, Any]:
        """Who qualifies, READ from the run that decided it.

        This used to replay both certified methods over every employee on each
        page load. The answer was already in `employee_eligibility` — written by
        the run, under the rule pack the run recorded — so recomputing it risked
        a second opinion about a number that has already been certified, and
        cost an engine pass over 10,236 employees to get there.

        Three statements in one round trip: the summary, which the filters must
        never move, the page, and how many rows the filter matched.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "summary": None, "rows": [], "matching": 0}

        summary_rows, page_rows, matching_rows = self._batch([
            _stmt_eligibility_summary(
                client_id, tax_year, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
            ),
            _stmt_eligibility_page(
                client_id, tax_year, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
                status, near_floor, q, limit, offset, sort, order,
            ),
            _stmt_eligibility_matching(
                client_id, tax_year, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
                status, near_floor, q,
            ),
        ])
        summary = summary_rows[0] if summary_rows else None
        # A run exists but holds no row for THIS year. The client was assessed;
        # this year was not, and those are different answers.
        if summary is None or not int(summary.get("employees_evaluated") or 0):
            return {"run": run, "summary": None, "rows": [], "matching": 0}
        return {
            "run": run,
            "summary": summary,
            "rows": page_rows,
            "matching": int(matching_rows[0]["total"]) if matching_rows else 0,
        }

    def employee_drill(
        self, client_id: int, *, tax_year: int, record_token: str
    ) -> dict[str, Any]:
        """One employee's derivation, READ, in a single round trip.

        Resolution is a LOOKUP: `record_token` is stored on every employee-grain
        table. The old path re-minted a token for all 10,236 employees in the
        client-year and matched — on top of loading the payroll twice and
        replaying both certified methods, per click.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "verdicts": [], "segments": [], "periods": []}

        verdicts, segments, periods, summary_rows = self._batch([
            _stmt_drill_verdicts(client_id, tax_year, run["run_id"], record_token),
            _stmt_drill_segments(client_id, tax_year, run["run_id"], record_token),
            _stmt_drill_periods(client_id, tax_year, run["run_id"], record_token),
            # The run's measuring dates, as the matrix beside the drill reads
            # them. Both methods measure the same twelve, so one row answers.
            _stmt_method_summary(client_id, tax_year, "min_max", run["run_id"]),
        ])
        month_ends: list[str] = []
        summary = summary_rows[0] if summary_rows else None
        if summary and summary.get("month_ends"):
            try:
                month_ends = list(json.loads(str(summary["month_ends"])))
            except (ValueError, TypeError):
                month_ends = []
        return {
            "run": run,
            "verdicts": verdicts,
            "segments": segments,
            "periods": periods,
            "month_ends": month_ends,
        }

    def unit_drill(
        self,
        client_id: int,
        worksite_id: str,
        *,
        tax_year: int,
        method: str,
        month: int | None = None,
        sort: str | None = None,
        order: str | None = None,
        near_min_hours: float | None = None,
        limit: int | None = None,
        employee_filters: str | None = None,
        near_filters: str | None = None,
    ) -> dict[str, Any]:
        """Everything the unit drawer renders, in TWO round trips.

        `unit` rides in the first batch even though the early exits may discard
        it: the trip is already being made, and a third trip costs more than the
        wasted statement.

        The two cohorts filter INDEPENDENTLY. They are different questions about
        different populations, and one shared filter would let a narrowing of
        the qualified list silently change the near-miss count under a tab
        nobody was looking at.
        """
        run_rows, in_flight_rows, unit_rows, year_rows = self._batch([
            _stmt_latest_run(client_id),
            _stmt_run_in_flight(client_id),
            _stmt_unit(client_id, worksite_id, tax_year, method),
            _stmt_client_year_rows(client_id, tax_year, method),
        ])
        run = run_rows[0] if run_rows else None
        in_flight = in_flight_rows[0] if in_flight_rows else None
        unit = unit_rows[0] if unit_rows else None
        year_held = bool(year_rows and int(year_rows[0]["total"]) > 0)
        if run is None or not year_held:
            return {"run": run if year_held else None, "in_flight": in_flight,
                    "unit": None, "employees": [], "months": None,
                    "near_threshold": [], "employees_total": 0, "near_total": 0,
                    "year_held": year_held}

        employees, months, near = self._batch([
            _stmt_unit_employees(
                client_id, worksite_id, tax_year, method, run["run_id"], month,
                sort=sort, order=order, limit=limit, filters=employee_filters,
            ),
            _stmt_unit_months(client_id, worksite_id, tax_year, method, run["run_id"]),
            _stmt_unit_near_threshold(
                client_id, worksite_id, tax_year, method, run["run_id"],
                sort=sort, order=order, near_min_hours=near_min_hours, limit=limit,
                filters=near_filters,
            ),
        ])
        # The denominator behind "12 of 37". Only issued when a filter is in
        # force: unfiltered, the rows on screen ARE the population, and a count
        # that can only ever agree with len(rows) is a statement nobody needs.
        totals: list[Statement] = []
        if employee_filters:
            totals.append(_stmt_unit_employees(
                client_id, worksite_id, tax_year, method, run["run_id"], month,
                count_only=True,
            ))
        if near_filters:
            totals.append(_stmt_unit_near_threshold(
                client_id, worksite_id, tax_year, method, run["run_id"],
                near_min_hours=near_min_hours, count_only=True,
            ))
        counted = self._batch(totals) if totals else []
        read_total = iter(counted)

        def unfiltered(rows: list[dict[str, Any]], asked: str | None) -> int:
            if not asked:
                return len(rows)
            found = next(read_total, None)
            return int(found[0]["total"]) if found else len(rows)

        return {
            "run": run,
            "in_flight": in_flight,
            "unit": unit,
            "employees": employees,
            "months": months[0] if months else None,
            "near_threshold": near,
            "employees_total": unfiltered(employees, employee_filters),
            "near_total": unfiltered(near, near_filters),
            "year_held": True,
        }

    def employee(
        self, record_token: str, *, client_id: int, tax_year: int, run_id: str
    ) -> list[dict[str, Any]]:
        """One employee's eligibility rows — one per method — for a run."""
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT * FROM {GOLD_SCHEMA}.employee_eligibility "
                    f"WHERE record_token = ? AND client_id = ? AND tax_year = ? "
                    f"AND run_id = ? ORDER BY method",
                    [record_token, client_id, tax_year, run_id],
                )
                return _rows(cursor)
            finally:
                cursor.close()

    def employee_units(
        self, record_token: str, *, client_id: int, tax_year: int, run_id: str, method: str
    ) -> list[dict[str, Any]]:
        months = ", ".join(f"month_{index:02d}" for index in range(1, 13))
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT worksite_id, entity_fein, first_pps, last_ppe, weight, {months} "
                    f"FROM {GOLD_SCHEMA}.onezero_matrix "
                    f"WHERE record_token = ? AND client_id = ? AND tax_year = ? "
                    f"AND run_id = ? AND method = ? ORDER BY worksite_id",
                    [record_token, client_id, tax_year, run_id, method],
                )
                return _rows(cursor)
            finally:
                cursor.close()


def run_envelope(
    run: dict[str, Any] | None,
    in_flight: dict[str, Any] | None,
    *,
    has_rows: bool = True,
) -> dict[str, Any]:
    """The provenance block every screen shows above its figures.

    `produced_at` answers "when was this true"; `in_flight` answers "is a newer
    answer coming". A figure with neither is a number with no date on it.

    `has_rows` is what keeps the year honest. The run is resolved per client, so
    a client with any current run would otherwise report every year as
    calculated — including years its payroll never covered. Candle Bottle holds
    TY2023 only, and its TY2024 must still say nobody has looked.
    """
    calculated = bool(run) and has_rows
    return {
        "calculation_state": "calculated" if calculated else "not_calculated",
        "run": {
            "run_id": run["run_id"],
            "produced_at": run["run_completed_at"],
            "started_at": run["run_started_at"],
            "calculation_id": run["calculation_id"],
            "code_commit": run["code_commit"],
            "rule_pack_version": run["rule_pack_version"],
            "step1_assumption_set_id": run["step1_assumption_set_id"],
            "onezero_assumption_set_id": run["onezero_assumption_set_id"],
            "triggered_by": run["triggered_by"],
            # What the run was ASKED FOR. Provenance, not the set of years it
            # produced — see `_stmt_latest_run`.
            "tax_year": run["tax_year"],
            "program_code": run["program_code"],
        } if run else None,
        "newer_run_in_flight": bool(in_flight),
        "in_flight": in_flight,
        "message": None if calculated else (
            "Not yet calculated. Run the calculation to see figures."
        ),
    }
