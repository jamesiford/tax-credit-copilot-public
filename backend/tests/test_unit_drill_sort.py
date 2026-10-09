"""Sorting and the near-threshold band happen in SQL, not in Python.

Cascade's unit has 22 employees; Candle Bottle holds 10,236 across 101 units.
Ordering them after fetching them is the same problem one layer down.

The band arrives as an ABSOLUTE hours figure. The caller subtracts whatever it
considers "close" from the statutory minimum the endpoint already hands back in
`thresholds` -- a literal 35 here would make Georgia's floor everyone's.
"""
from __future__ import annotations

import pytest

from infrastructure.persistence import gold_reader as gr


def _employees(**kwargs):
    sql, values = gr._stmt_unit_employees(
        1001, "GA_GA-010", 2023, "min_max", "run-1", None, **kwargs
    )
    return " ".join(sql.split()), values


def _near(**kwargs):
    sql, values = gr._stmt_unit_near_threshold(
        1001, "GA_GA-010", 2023, "min_max", "run-1", **kwargs
    )
    return " ".join(sql.split()), values


# --- ordering --------------------------------------------------------------


@pytest.mark.parametrize("key,column", [
    ("avg_weekly_hours", "e.avg_weekly_hours"),
    ("avg_weekly_wages", "e.avg_weekly_wages"),
    ("employee_id", "m.employee_id"),
])
def test_each_sortable_column_reaches_the_order_by(key, column):
    sql, _ = _employees(sort=key)

    assert f"ORDER BY {column} DESC" in sql


def test_order_direction_is_honoured():
    assert "ORDER BY e.avg_weekly_hours ASC" in _employees(order="asc")[0]
    assert "ORDER BY e.avg_weekly_hours DESC" in _employees(order="desc")[0]


def test_an_unknown_sort_falls_back_rather_than_reaching_sql():
    """The value arrives from a query string. It must never be interpolated."""
    sql, _ = _employees(sort="employee_id; DROP TABLE tcc_gold.unit_year_master")

    assert "DROP" not in sql.upper()
    assert "ORDER BY e.avg_weekly_hours" in sql


def test_the_sort_carries_a_stable_tiebreak():
    """Without one, two reads of the same sort can repeat or drop a row."""
    sql, _ = _employees(sort="avg_weekly_hours")

    assert sql.rstrip().endswith("m.employee_id")


def test_sorting_on_the_tiebreak_does_not_name_it_twice():
    """SQL Server rejects a column listed twice in one ORDER BY, which turned
    `sort=employee_id` into a 500 against live Fabric."""
    sql, _ = _employees(sort="employee_id")

    assert sql.count("m.employee_id ") + sql.count("m.employee_id,") <= 1 or (
        sql.split("ORDER BY")[1].count("employee_id") == 1
    )
    assert sql.split("ORDER BY")[1].strip() == "m.employee_id DESC"


def test_the_near_cohort_also_avoids_the_duplicate_tiebreak():
    sql, _ = _near(sort="employee_id", order="asc")

    assert sql.split("ORDER BY")[1].strip() == "e.employee_id ASC"


def test_the_near_threshold_cohort_sorts_on_its_own_alias():
    """It reads `employee_eligibility` alone, so there is no `m` to order by."""
    sql, _ = _near(sort="employee_id")

    assert "ORDER BY e.employee_id" in sql
    assert "m.employee_id" not in sql


# --- the band --------------------------------------------------------------


def test_the_band_is_a_bound_parameter_not_a_literal():
    sql, values = _near(near_min_hours=30.0)

    assert "e.avg_weekly_hours >= ?" in sql
    assert 30.0 in values


def test_no_statutory_floor_is_written_into_the_query():
    """Georgia's 35 is a rule-pack value, not a warehouse constant."""
    sql, _ = _near(near_min_hours=30.0)

    assert "35" not in sql


def test_the_band_is_absent_unless_asked_for():
    sql, values = _near()

    assert "avg_weekly_hours >=" not in sql
    assert 30.0 not in values


# --- the row cap -----------------------------------------------------------


def test_a_limit_caps_the_rows_in_sql():
    sql, _ = _employees(limit=25)

    assert sql.startswith("SELECT TOP 25 ")


def test_the_limit_is_an_integer_even_when_it_arrives_as_text():
    """It is concatenated rather than bound -- TOP takes no parameter here."""
    sql, _ = _employees(limit="25")

    assert "TOP 25" in sql


def test_no_cap_is_applied_by_default():
    assert "TOP" not in _employees()[0]
    assert "TOP" not in _near()[0]


def test_the_near_cohort_keeps_its_distinct_when_capped():
    """`employee_period_fact` is one row per pay period, so the join fans out."""
    sql, _ = _near(limit=10)

    assert sql.startswith("SELECT DISTINCT TOP 10 ")
