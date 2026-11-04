"""Who qualifies: the pivot over `employee_eligibility`, its classification, filters and page."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import Statement


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
