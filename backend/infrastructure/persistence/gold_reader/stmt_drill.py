"""One employee's derivation: verdicts, segments and pay periods, by record token."""
from __future__ import annotations

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import Statement


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
