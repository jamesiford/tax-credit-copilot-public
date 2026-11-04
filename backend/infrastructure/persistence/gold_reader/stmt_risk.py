"""The people near a floor: those inside the credit who could fall out, and those outside who could reach it."""
from __future__ import annotations

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import Statement


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
