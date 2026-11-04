"""The generic query returns what the fixed capabilities return, on the REAL engine's output. [CH-16e]

The semantic model and the fixed tools both describe the same Gold rows. Where they overlap
(eligible counts per method, credit per tax year and per unit-year, headcount per month, the
annual average) they must agree to the digit, or the agent can be handed two answers to one
question. A mismatch here is a bug in the semantic model or the builder, never in the engine:
the fixed side is the authority and the pinned parity figures are not touched.

The store is the synthetic payroll replayed through `RunClientCalculationCommand`, written by the
real `GoldWriter`, read by the real `GoldReader` (see `tests/data_engine_fixture.py` for the
two differences from the deployed path). One run serves the module.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from application import wiring
from application.capabilities.client_analysis import client_trend
from application.capabilities.client_eligibility import client_eligibility
from application.capabilities.invoke import invoke
from application.data_wiring import set_data_query_service
from tests.data_caps_fixture import person
from tests.data_engine_fixture import CLIENT, YEAR, SqliteGoldReader, SqliteWarehouse, data_service, run_engine

METHODS = ("min_max", "pay_period")
MONTHS = tuple(f"month_{n:02d}" for n in range(1, 13))


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    warehouse = SqliteWarehouse()
    run_engine(warehouse, tmp_path_factory.mktemp("equivalence"))
    wiring.set_gold_reader(SqliteGoldReader(warehouse))
    set_data_query_service(data_service(warehouse))
    try:
        yield warehouse
    finally:
        wiring.set_gold_reader(None)
        set_data_query_service(None)


def rows(**spec) -> list[dict]:
    """The rows `data_query` returns for `spec`, through the full tool path (schema, lanes, render)."""
    facts = invoke("data_query", {"client_id": CLIENT, **spec}, person()).to_dict()["facts"]
    assert not facts["truncated"], "a capped result cannot be an equivalence witness"
    return facts["rows"]


def exact(value) -> Decimal:
    """Both sides as Decimals, so a float's repr cannot hide or invent a difference."""
    return Decimal(str(value))


def month_sums(by: str, method: str, year: int, dataset: str = "unit_month_summary") -> dict:
    """Each month's summed headcount, per `by` (a dimension) or overall (`""`), in the two-query split the measure cap needs."""
    merged: dict = {}
    for chunk in (MONTHS[:6], MONTHS[6:]):
        got = rows(dataset=dataset, select=[by] if by else [], tax_years=[year], method=method,
                   measures=[{"column": m, "agg": "sum", "as": m} for m in chunk])
        for row in got:
            merged.setdefault(row[by] if by else "", {}).update({m: row[m] for m in chunk})
    return merged


# ----------------------------------------------------------- eligible counts per method


def test_eligible_counts_per_method_and_year_equal_the_trend(store):
    seen = 0
    for method in METHODS:
        trend = {y["tax_year"]: y for y in client_trend(CLIENT, method).to_dict()["facts"]["years"]}
        got = rows(dataset="employee_eligibility", select=["tax_year"], method=method,
                   filters=[{"column": "eligible", "op": "eq", "value": True}], measures=[{"column": "*", "agg": "count", "as": "n"}])
        assert {r["tax_year"]: r["n"] for r in got} == {y: t["eligible_employees"] for y, t in trend.items()}
        evaluated = rows(dataset="employee_eligibility", select=["tax_year"], method=method, measures=[{"column": "*", "agg": "count", "as": "n"}])
        assert {r["tax_year"]: r["n"] for r in evaluated} == {y: t["employees_evaluated"] for y, t in trend.items()}
        seen += len(trend)
    assert seen == 4, "two years under two methods, or this proves nothing"


def test_the_run_summary_dataset_agrees_with_the_trend_it_feeds(store):
    for method in METHODS:
        trend = {y["tax_year"]: y for y in client_trend(CLIENT, method).to_dict()["facts"]["years"]}
        got = {r["tax_year"]: r for r in rows(
            dataset="run_method_summary", select=["tax_year"], method=method,
            measures=[{"column": c, "agg": "max", "as": c} for c in ("eligible_employees", "employees_evaluated", "annual_average")])}
        assert set(got) == set(trend)
        for year, line in trend.items():
            assert got[year]["eligible_employees"] == line["eligible_employees"]
            assert got[year]["employees_evaluated"] == line["employees_evaluated"]
            assert exact(got[year]["annual_average"]) == exact(line["annual_average"])


def test_the_population_counts_of_the_eligibility_tool_equal_the_query(store):
    population = client_eligibility(CLIENT, YEAR, "GA", "min_max", include_population=True).to_dict()["facts"]["population"]
    eligible = {r["method"]: r["n"] for r in rows(
        dataset="employee_eligibility", select=["method"], tax_years=[YEAR],
        filters=[{"column": "eligible", "op": "eq", "value": True}], measures=[{"column": "*", "agg": "count", "as": "n"}])}
    evaluated = {r["method"]: r["n"] for r in rows(
        dataset="employee_eligibility", select=["method"], tax_years=[YEAR], measures=[{"column": "*", "agg": "count", "as": "n"}])}
    assert eligible == {"min_max": population["min_max_eligible"], "pay_period": population["pay_period_eligible"]}
    assert set(evaluated.values()) == {population["employees_evaluated"]}


def test_the_methods_stay_labelled_and_are_never_merged(store):
    both = rows(dataset="employee_eligibility", select=["tax_year", "method"], tax_years=[YEAR],
                filters=[{"column": "eligible", "op": "eq", "value": True}], measures=[{"column": "*", "agg": "count", "as": "n"}])
    assert {r["method"] for r in both} == set(METHODS) and len(both) == 2


def test_the_comparison_can_fail(store):
    """A negative control: one method's query against the other method's trend must NOT match."""
    trend = {y["tax_year"]: y["eligible_employees"] for y in client_trend(CLIENT, "pay_period").to_dict()["facts"]["years"]}
    got = rows(dataset="employee_eligibility", select=["tax_year"], method="min_max",
               filters=[{"column": "eligible", "op": "eq", "value": True}], measures=[{"column": "*", "agg": "count", "as": "n"}])
    assert {r["tax_year"]: r["n"] for r in got} != trend


# ------------------------------------------------------------------- credit totals


def test_credit_per_tax_year_equals_the_trend(store):
    for method in METHODS:
        trend = {y["tax_year"]: exact(y["annual_credit_usd"]) for y in client_trend(CLIENT, method).to_dict()["facts"]["years"]}
        got = rows(dataset="unit_year_master", select=["tax_year"], method=method, measures=[{"column": "annual_credit_usd", "agg": "sum", "as": "credit"}])
        assert {r["tax_year"]: exact(r["credit"]) for r in got} == trend
        assert any(v > 0 for v in trend.values()), "a credit of zero in every year would make this vacuous"


def test_credit_per_unit_year_equals_the_units_grid_read(store):
    reader, checked = wiring.get_gold_reader(), 0
    for method in METHODS:
        grid, total = reader.unit_years(CLIENT, method=method, limit=500)
        got = rows(dataset="unit_year_master", select=["worksite_id", "tax_year"], method=method,
                   measures=[{"column": "annual_credit_usd", "agg": "sum", "as": "credit"}, {"column": "average_headcount", "agg": "sum", "as": "avg"}])
        assert len(got) == total == len(grid)
        by_unit = {(r["worksite_id"], r["tax_year"]): (exact(r["credit"]), exact(r["avg"])) for r in got}
        assert by_unit == {(g["worksite_id"], g["tax_year"]): (exact(g["annual_credit_usd"]), exact(g["average_headcount"])) for g in grid}
        checked += total
    assert checked >= 16


def test_the_lifetime_tranches_equal_the_installment_read(store):
    reader = wiring.get_gold_reader()
    for method in METHODS:
        installments = reader.installments(CLIENT, method=method)
        got = rows(dataset="unit_credit_installment", select=["worksite_id", "tax_year"], method=method,
                   measures=[{"column": "claimable_usd", "agg": "sum", "as": "claimable"}])
        expected: dict = {}
        for line in installments:
            key = (line["worksite_id"], line["tax_year"])
            expected[key] = expected.get(key, Decimal(0)) + exact(line["claimable_usd"])
        assert {(r["worksite_id"], r["tax_year"]): exact(r["claimable"]) for r in got} == expected


# ---------------------------------------------------------------- headcount per month


def test_headcount_per_month_equals_the_series_the_eligibility_read_uses(store):
    reader, checked = wiring.get_gold_reader(), 0
    for method in METHODS:
        for year in (YEAR - 1, YEAR):
            series = reader.headcount_series(CLIENT, tax_year=year, method=method)["months"]
            got = month_sums("", method, year)[""]
            assert [exact(got[m]) for m in MONTHS] == [exact(v) for v in series], (method, year)
            checked += 1
    assert checked == 4


def test_headcount_per_month_and_unit_equals_the_grid_rows(store):
    reader = wiring.get_gold_reader()
    run_id = reader.latest_run(CLIENT)["run_id"]
    for method in METHODS:
        grid = {r["worksite_id"]: r for r in reader.month_summaries(CLIENT, method=method, run_id=run_id, tax_year=YEAR)}
        got = month_sums("worksite_id", method, YEAR)
        assert set(got) == set(grid) and len(grid) == 4
        for site, line in grid.items():
            assert [exact(got[site][m]) for m in MONTHS] == [exact(line[m]) for m in MONTHS], (method, site)


def test_the_annual_average_equals_what_the_eligibility_tool_reports(store):
    for method in METHODS:
        said = client_eligibility(CLIENT, YEAR, "GA", method).to_dict()["facts"]["snapshot"]["average_headcount"]
        got = rows(dataset="run_method_summary", select=["tax_year"], tax_years=[YEAR], method=method, measures=[{"column": "annual_average", "agg": "max", "as": "a"}])
        assert exact(got[0]["a"]) == exact(said)


def test_the_matrix_summed_by_worksite_is_the_monthly_summary_the_model_says_it_is(store):
    """`onezero_matrix`'s engine note says its month columns sum to `unit_month_summary`; hold it to that."""
    for method in METHODS:
        matrix = month_sums("worksite_id", method, YEAR, dataset="onezero_matrix")
        summary = month_sums("worksite_id", method, YEAR)
        assert matrix == summary, method
