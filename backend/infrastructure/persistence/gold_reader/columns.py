"""Column sets, and where a warehouse value becomes JSON.

`_MONEY_COLUMNS` and `_BOOL_COLUMNS` type a value by its column NAME, which is why a SQL
alias that borrows one is a bug (see `tests/test_api_v2_gold_reads.py`); `month_ends_of`
reads the one JSON-bearing column the run writes.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any



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


def month_ends_of(summary: dict[str, Any] | None) -> list[str]:
    """The run's REAL measuring dates from a `run_method_summary` row; empty when it holds none.

    A client whose fiscal year opens in August has no August-to-December meaning, and
    counting elapsed months off 1 January would misplace every one.
    """
    if summary and summary.get("month_ends"):
        try:
            return list(json.loads(str(summary["month_ends"])))
        except (ValueError, TypeError):
            return []
    return []


Statement = tuple[str, list[Any]]

#: SQLSTATEs meaning "the link is gone", as opposed to "your SQL is wrong".
#: Only these are retried; a syntax error retried is a syntax error twice.
_CONNECTION_LOST_STATES = frozenset({"08S01", "08003", "08001", "01000", "HYT00"})
