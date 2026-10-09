"""The `filter=` grammar, and the SQL it compiles to.

Two properties matter more than the parsing, and both are asserted here:

* **The column name is never interpolated unless it matched a whitelist.** The
  value arrives from a query string, so a name the endpoint did not declare must
  not reach the statement at all, and every value must be a bound parameter.
* **An unparseable term is DROPPED, not widened.** A predicate that silently
  matches everything is worse than no filter: the page says it is filtering and
  the total says otherwise.

These run offline. They read the statement text rather than a warehouse, which
is the point — the filtering has to be IN the SQL, and a test that fetched rows
and counted them would pass just as well if it happened in Python.
"""
from __future__ import annotations

import pytest

from infrastructure.persistence.gold_reader import (
    EMPLOYEE_FILTERS,
    NEAR_FILTERS,
    _stmt_unit_employees,
    _stmt_unit_near_threshold,
)
from tools.grid_filter import compile_filters

ARGS = (1001, "GA_GA-001", 2023, "min_max", "run-1")


def employees(**kwargs):
    return _stmt_unit_employees(*ARGS, None, **kwargs)


class TestTheGrammar:
    def test_a_comparator_compiles_to_a_bound_predicate(self):
        sql, values, applied = compile_filters("avg_weekly_hours:>=35", EMPLOYEE_FILTERS)
        assert sql == " AND (e.avg_weekly_hours >= ?)"
        assert values == [35.0]
        assert applied == {"avg_weekly_hours": ">=35"}

    def test_a_range_compiles_to_two_bounds(self):
        sql, values, _ = compile_filters("weeks_worked:10..52", EMPLOYEE_FILTERS)
        assert sql == " AND (e.weeks_worked >= ? AND e.weeks_worked <= ?)"
        assert values == [10.0, 52.0]

    def test_the_bounds_are_ordered_however_they_arrive(self):
        _, values, _ = compile_filters("weeks_worked:52..10", EMPLOYEE_FILTERS)
        assert values == [10.0, 52.0]

    def test_a_bare_number_reads_as_at_least_matching_the_browser(self):
        sql, values, _ = compile_filters("weeks_worked:10", EMPLOYEE_FILTERS)
        assert sql == " AND (e.weeks_worked >= ?)"
        assert values == [10.0]

    def test_text_becomes_a_lowered_like(self):
        sql, values, _ = compile_filters("employee_id:~E001", EMPLOYEE_FILTERS)
        assert sql == " AND (LOWER(m.employee_id) LIKE ?)"
        assert values == ["%e001%"]

    def test_an_enum_becomes_an_in_list_with_one_mark_per_value(self):
        sql, values, _ = compile_filters("employee_id:A|B", {"employee_id": ("e.x", "enum")})
        assert sql == " AND (e.x IN (?, ?))"
        assert values == ["A", "B"]

    def test_several_terms_are_anded_so_each_one_narrows_the_last(self):
        sql, values, applied = compile_filters(
            "weeks_worked:>=10;avg_weekly_hours:<40", EMPLOYEE_FILTERS
        )
        assert sql == " AND (e.weeks_worked >= ?) AND (e.avg_weekly_hours < ?)"
        assert values == [10.0, 40.0]
        assert len(applied) == 2


class TestWhatItRefuses:
    def test_a_column_off_the_whitelist_never_reaches_the_statement(self):
        sql, values, applied = compile_filters("salary:>=100", EMPLOYEE_FILTERS)
        assert (sql, values, applied) == ("", [], {})

    def test_an_injection_attempt_is_simply_an_unknown_column(self):
        sql, values, _ = compile_filters("1=1 OR x:>=1;DROP TABLE t:~a", EMPLOYEE_FILTERS)
        assert sql == ""
        assert values == []

    def test_an_unreadable_value_is_dropped_rather_than_matching_everything(self):
        sql, _, applied = compile_filters("weeks_worked:banana", EMPLOYEE_FILTERS)
        assert sql == ""
        assert applied == {}

    def test_like_wildcards_in_a_needle_are_escaped_not_honoured(self):
        # Otherwise a filter can widen itself: `%` would match every employee
        # while the chip still claims to be narrowing.
        _, values, _ = compile_filters("employee_id:~%_", EMPLOYEE_FILTERS)
        assert values == ["%[%][_]%"]

    @pytest.mark.parametrize("wire", ["", None, "  ", "nocolon", ":"])
    def test_nothing_at_all_compiles_to_nothing_at_all(self, wire):
        assert compile_filters(wire, EMPLOYEE_FILTERS) == ("", [], {})


class TestTheStatementItself:
    def test_the_predicate_lands_in_the_where_not_in_python(self):
        sql, values = employees(filters="avg_weekly_hours:>=35")
        assert "e.avg_weekly_hours >= ?" in sql
        assert values[-1] == 35.0

    def test_the_predicate_precedes_the_order_by(self):
        # SQL Server rejects a WHERE after an ORDER BY, so this is not a style
        # preference — it is whether the statement runs at all.
        sql, _ = employees(filters="weeks_worked:>=10", sort="employee_id")
        assert sql.index("e.weeks_worked >= ?") < sql.index("ORDER BY")

    def test_an_unfiltered_read_adds_no_clause(self):
        plain, plain_values = employees()
        assert "ORDER BY" in plain
        assert len(plain_values) == 5

    def test_the_count_carries_the_same_predicate_so_the_denominator_is_the_same_population(self):
        rows_sql, rows_values = employees(filters="weeks_worked:>=10")
        count_sql, count_values = employees(filters="weeks_worked:>=10", count_only=True)
        assert count_sql.startswith("SELECT COUNT(*) AS total")
        assert count_values == rows_values

    def test_the_count_carries_no_order_by(self):
        count_sql, _ = employees(count_only=True, sort="employee_id", limit=50)
        assert "ORDER BY" not in count_sql
        assert "TOP" not in count_sql

    def test_the_near_count_wraps_the_distinct_in_a_derived_table(self):
        # DISTINCT cannot be counted in place, and there must be no ORDER BY
        # inside the subquery or SQL Server refuses it.
        sql, _ = _stmt_unit_near_threshold(*ARGS, count_only=True)
        assert sql.startswith("SELECT COUNT(*) AS total FROM (SELECT DISTINCT")
        assert "ORDER BY" not in sql

    def test_the_two_cohorts_alias_the_same_column_differently(self):
        # `employee_id` is on the matrix in one and on eligibility in the other.
        # One shared map would produce an unknown alias in whichever it was not
        # written for.
        assert EMPLOYEE_FILTERS["employee_id"][0] == "m.employee_id"
        assert NEAR_FILTERS["employee_id"][0] == "e.employee_id"

    def test_the_near_statement_filters_without_disturbing_the_band(self):
        sql, values = _stmt_unit_near_threshold(
            *ARGS, near_min_hours=30.0, filters="weeks_worked:>=10"
        )
        assert values[-2:] == [30.0, 10.0]
        assert sql.count("e.avg_weekly_hours >= ?") == 1

    def test_every_filterable_column_is_a_column_the_statement_selects(self):
        sql, _ = employees()
        for name, (expression, _kind) in EMPLOYEE_FILTERS.items():
            assert expression.split(".", 1)[1] in sql, name
