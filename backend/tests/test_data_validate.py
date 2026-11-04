"""Validation: every way a specification can be wrong is a precise, typed refusal. [CH-16b]"""
from __future__ import annotations

import pytest

from application.data import errors as E
from application.data.classify import BOTH, USER, employee_level_labels, result_audience
from application.data.semantic_model import Agg, Op, default_model
from application.data.spec import MAX_FILTERS, MAX_GROUP_BY, MAX_IN_VALUES, MAX_MEASURES, MAX_ORDER_BY, MAX_SELECT, QuerySpec
from application.data.validate import validate

MODEL = default_model()


DEFAULT_SELECT = {"unit_year_master": "worksite_id", "location": "location_id", "payroll": "location_id", "pay_code": "pay_code_id"}


def spec(dataset="unit_year_master", **changes) -> QuerySpec:
    first = DEFAULT_SELECT.get(dataset, "tax_year")
    payload = {"dataset": dataset, "client_id": 1001, "select": [first], **changes}
    return QuerySpec.from_dict({k: v for k, v in payload.items() if v is not None})


def refused(error, **kw):
    with pytest.raises(error) as caught:
        validate(spec(**kw), MODEL, known_years=kw.pop("known", None))
    return caught.value


def count(**extra):
    return {"measures": [{"column": "*", "agg": "count"}], **extra}


def test_a_plain_query_validates_into_a_plan():
    plan = validate(spec(**count(tax_years=[2023])), MODEL)
    assert plan.client_id == 1001 and plan.tax_years == (2023,) and plan.limit == 100
    assert [c.label for c in plan.result_columns] == ["method", "worksite_id", "row_count"]


def test_a_dataset_with_two_readings_always_returns_and_groups_by_method():
    plan = validate(spec(measures=[{"column": "annual_credit_usd", "agg": "sum"}]), MODEL)
    assert plan.method == "both" and plan.select[0].label == "method" and plan.group_by[0].label == "method"
    pinned = validate(spec(method="pay_period", **count(group_by=["worksite_id"])), MODEL)
    assert pinned.method == "pay_period" and [r.label for r in pinned.group_by] == ["method", "worksite_id"]


@pytest.mark.parametrize("changes, error", [
    ({"dataset": "employees"}, E.UnknownDataset),
    ({"select": ["nope"]}, E.UnknownColumn),
    ({"select": ["worksite_id; DROP TABLE x"]}, E.UnknownColumn),
    ({"select": ["a.b.c"]}, E.UnknownColumn),
    ({"select": ["nojoin.worksite_id"]}, E.UnknownColumn),
    ({"filters": [{"column": "nope", "op": "eq", "value": 1}]}, E.UnknownColumn),
    ({"measures": [{"column": "nope", "agg": "sum"}]}, E.UnknownColumn),
    ({"select": ["worksite_id"], "group_by": ["nope"]}, E.UnknownColumn),
    ({"dataset": "employee_eligibility", "select": ["employee_id"]}, E.BlockedColumn),
    ({"dataset": "employee_eligibility", "select": ["tax_year"], "filters": [{"column": "employee_id", "op": "eq", "value": "x"}]}, E.BlockedColumn),
    ({"dataset": "employee_eligibility", "select": ["tax_year"], "group_by": ["employee_id"]}, E.BlockedColumn),
    ({"dataset": "employee_eligibility", "select": ["tax_year"], "measures": [{"column": "employee_id", "agg": "count"}]}, E.BlockedColumn),
    ({"dataset": "run_manifest", "select": ["triggered_by"]}, E.BlockedColumn),
    ({"dataset": "payroll", "select": ["client_employee_id"]}, E.BlockedColumn),
    ({"dataset": "payroll", "select": ["employee_id"]}, E.BlockedColumn),
    ({"filters": [{"column": "worksite_id", "op": "contains", "value": "a"}]}, E.OperatorNotAllowed),
    ({"filters": [{"column": "worksite_id", "op": "between", "value": ["a", "b"]}]}, E.OperatorNotAllowed),
    ({"filters": [{"column": "qualified", "op": "gte", "value": True}]}, E.OperatorNotAllowed),
    ({"filters": [{"column": "run_id", "op": "eq", "value": "x"}]}, E.OperatorNotAllowed),
    ({"filters": [{"column": "tax_year", "op": "like", "value": 1}]}, E.OperatorNotAllowed),
    ({"measures": [{"column": "worksite_id", "agg": "sum"}]}, E.AggregationNotAllowed),
    ({"measures": [{"column": "qualified", "agg": "avg"}]}, E.AggregationNotAllowed),
    ({"measures": [{"column": "*", "agg": "sum"}]}, E.AggregationNotAllowed),
    ({"measures": [{"column": "tax_year", "agg": "median"}]}, E.AggregationNotAllowed),
    (count(group_by=["average_headcount"], select=["average_headcount"]), E.GroupByMeasure),
    (count(select=["average_headcount"]), E.GroupByMeasure),
    (count(select=["worksite_id", "tax_year"], group_by=["worksite_id"]), E.SelectNotGrouped),
    ({"select": ["worksite_id"], "group_by": ["tax_year"]}, E.SelectNotGrouped),
    ({"order_by": ["tax_year"]}, E.OrderByOutsideSelection),
    (count(order_by=["nope"]), E.OrderByOutsideSelection),
    ({"limit": 501}, E.LimitTooHigh),
    ({"limit": 0}, E.MalformedSpec),
    ({"limit": -3}, E.MalformedSpec),
    ({"client_id": None}, E.MissingClient),
    ({"client_id": 0}, E.MalformedSpec),
    ({"tax_years": [1999]}, E.TaxYearOutOfRange),
    ({"tax_years": [2101]}, E.TaxYearOutOfRange),
    ({"dataset": "payroll", "tax_years": [2023]}, E.TaxYearNotApplicable),
    ({"select": None}, E.EmptyQuery),
    ({"filters": [{"column": "tax_year", "op": "eq", "value": "2023"}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "eq", "value": True}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "eq", "value": 2023.5}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "qualified", "op": "eq", "value": 1}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "average_headcount", "op": "gte", "value": "many"}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "average_headcount", "op": "gte", "value": 1e999}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "between", "value": [2024, 2023]}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "between", "value": [2023]}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "eq", "value": [1, 2]}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "in", "value": []}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "tax_year", "op": "in", "value": 2023}]}, E.ValueTypeMismatch),
    ({"dataset": "location", "filters": [{"column": "open_date", "op": "eq", "value": "2023-02-30"}]}, E.ValueTypeMismatch),
    ({"dataset": "location", "filters": [{"column": "open_date", "op": "eq", "value": "01/02/2023"}]}, E.ValueTypeMismatch),
    ({"filters": [{"column": "status", "op": "eq", "value": "bogus"}]}, E.ValueNotAllowed),
    ({"method": "average"}, E.ValueTypeMismatch),
    ({"dataset": "payroll", "method": "min_max"}, E.MethodNotApplicable),
    (count(measures=[{"column": "*", "agg": "count", "as": "Robert'); DROP"}]), E.InvalidAlias),
    ({"measures": [{"column": "*", "agg": "count", "as": "1bad"}]}, E.InvalidAlias),
    ({"measures": [{"column": "*", "agg": "count", "as": "worksite_id"}], "group_by": ["worksite_id"]}, E.DuplicateName),
    ({"measures": [{"column": "*", "agg": "count"}, {"column": "*", "agg": "count"}]}, E.DuplicateName),
])
def test_each_way_a_specification_can_be_wrong_is_its_own_typed_error(changes, error):
    with pytest.raises(error):
        validate(spec(**changes), MODEL)


def test_a_year_the_client_has_no_data_for_is_refused_when_the_caller_knows_the_years():
    validate(spec(tax_years=[2023]), MODEL, known_years={2023, 2024})
    with pytest.raises(E.TaxYearOutOfRange):
        validate(spec(tax_years=[2022]), MODEL, known_years={2023, 2024})


@pytest.mark.parametrize("changes, cap", [
    ({"filters": [{"column": "tax_year", "op": "eq", "value": 2023}] * (MAX_FILTERS + 1)}, "filters"),
    ({"measures": [{"column": "*", "agg": "count", "as": f"m{i}"} for i in range(MAX_MEASURES + 1)]}, "measures"),
    ({"select": [f"c{i}" for i in range(MAX_SELECT + 1)]}, "select"),
    ({"group_by": [f"c{i}" for i in range(MAX_GROUP_BY + 1)]}, "group_by"),
    ({"order_by": [f"c{i}" for i in range(MAX_ORDER_BY + 1)]}, "order_by"),
    ({"filters": [{"column": "tax_year", "op": "in", "value": list(range(2000, 2000 + MAX_IN_VALUES + 1))}]}, "filters"),
])
def test_a_query_is_capped_in_every_dimension(changes, cap):
    with pytest.raises((E.TooManyItems, E.ValueTypeMismatch)):
        validate(spec(**changes), MODEL)


HOSTILE = [
    "'; DROP TABLE tcc_gold.unit_year_master; --", "1; SELECT * FROM sys.tables",
    "a UNION SELECT name FROM sys.objects", "x/* c */y", "x--y", "ＤＲＯＰ ＴＡＢＬＥ x", "ｓｅｌｅｃｔ * from t", "x；DROP", "a\x00b",
    "a\u202eb", "a\u200bb", "EXEC xp_cmdshell 'dir'", "x'; WAITFOR DELAY '0:0:5'--", "@@version",
]
#: Quote-shaped injection attempts. They are no longer refused (a quote cannot alter a bound
#: parameter, and the pattern that refused them also refused "Bakers' Group"); they must arrive as
#: the value, verbatim, and `test_data_build_sql` / `test_data_query_abuse` prove they stay out of the SQL text.
QUOTE_ONLY = ["x' OR '1'='1", "x\" OR \"1\"=\"1", "x' = '"]


@pytest.mark.parametrize("value", HOSTILE)
def test_a_value_that_looks_like_sql_is_refused_on_an_equality_filter(value):
    for op, payload in ((Op.EQ, value), (Op.IN, [value])):
        with pytest.raises((E.SqlLikeValue, E.ValueTypeMismatch)):
            validate(spec(filters=[{"column": "worksite_id", "op": op.value, "value": payload}]), MODEL)


@pytest.mark.parametrize("value", QUOTE_ONLY)
def test_a_quote_shaped_value_is_carried_as_the_value_because_it_is_bound(value):
    plan = validate(spec(filters=[{"column": "worksite_id", "op": "eq", "value": value}]), MODEL)
    assert plan.filters[0].value == value


def test_free_text_contains_accepts_sql_words_but_never_control_characters():
    ok = spec("employee_period_fact", select=["tax_year"], filters=[{"column": "job_title", "op": "contains", "value": "select manager"}])
    assert validate(ok, MODEL).filters[0].value == "select manager"
    for bad in ("a\x00b", "a\u202eb", "", "x" * 101):
        with pytest.raises(E.ValueTypeMismatch):
            validate(spec("employee_period_fact", select=["tax_year"], filters=[{"column": "job_title", "op": "contains", "value": bad}]), MODEL)


def test_a_declared_join_resolves_and_an_undeclared_one_does_not():
    plan = validate(spec("payroll", select=["location.location_name", "pay_code_info.pay_code"], **count()), MODEL)
    assert [j.decl.name for j in plan.joins] == ["location", "pay_code_info"]
    assert plan.select[0].label == "location__location_name"
    with pytest.raises(E.UnknownColumn):
        validate(spec("payroll", select=["employees.name"]), MODEL)
    with pytest.raises(E.UnknownColumn):
        validate(spec("location", select=["location.location_name"]), MODEL)


def test_ordering_may_name_a_selected_column_the_method_or_a_measure():
    plan = validate(spec(select=["worksite_id"], measures=[{"column": "annual_credit_usd", "agg": "sum", "as": "credit"}],
                         order_by=[{"column": "credit", "direction": "desc"}, "method", "worksite_id"]), MODEL)
    assert [(o.label, o.direction) for o in plan.order_by] == [("credit", "desc"), ("method", "asc"), ("worksite_id", "asc")]


def test_every_blocked_column_in_every_dataset_is_refused_in_every_position():
    for dataset in MODEL.datasets:
        for column in (c for c in dataset.columns if not c.queryable):
            for changes in ({"select": [column.logical]}, {"filters": [{"column": column.logical, "op": "eq", "value": "x"}]},
                            {"measures": [{"column": column.logical, "agg": "count"}]}, {"group_by": [column.logical]}):
                base = {"select": ["method"] if dataset.method_column else [dataset.columns[0].logical], **changes}
                with pytest.raises((E.BlockedColumn, E.SelectNotGrouped)) as caught:
                    validate(spec(dataset.name, **base), MODEL)
                assert caught.type is E.BlockedColumn or "group_by" in changes


def test_errors_carry_a_stable_code_and_the_field_and_never_echo_a_value():
    caught = refused(E.SqlLikeValue, filters=[{"column": "worksite_id", "op": "eq", "value": "x'; DROP TABLE t; --"}])
    assert caught.to_dict() == {"code": "sql_like_value", "message": caught.message, "field": "filters"}
    assert "DROP" not in caught.message
    unknown = refused(E.UnknownColumn, select=["secret_column_name"])
    assert "secret_column_name" not in unknown.message


AUDIENCE = [
    ("employee_eligibility", {"select": ["record_token"]}, USER),
    ("employee_eligibility", {"select": ["tax_year"]}, USER),
    ("employee_eligibility", {"select": ["tax_year"], "measures": [{"column": "*", "agg": "count"}]}, BOTH),
    ("employee_eligibility", {"select": ["record_token"], "measures": [{"column": "*", "agg": "count"}]}, USER),
    ("employee_eligibility", {"select": ["record_token"], "measures": [{"column": "total_wages", "agg": "sum"}]}, USER),
    ("onezero_matrix", {"select": ["worksite_id"], "measures": [{"column": "month_01", "agg": "sum"}]}, BOTH),
    ("employee_period_fact", {"select": ["worksite_id", "hours"]}, USER),
    ("payroll", {"select": ["pay_month"], "measures": [{"column": "wages", "agg": "avg"}]}, BOTH),
    ("payroll", {"select": ["pay_month"]}, USER),
    ("unit_year_master", {"select": ["worksite_id", "annual_credit_usd"]}, BOTH),
    ("location", {"select": ["location_name"]}, BOTH),
]


@pytest.mark.parametrize("dataset, changes, audience", AUDIENCE)
def test_a_result_is_for_the_person_only_when_it_carries_person_level_values(dataset, changes, audience):
    assert result_audience(validate(spec(dataset, **changes), MODEL)) == audience


def test_the_columns_a_model_must_not_be_handed_are_named():
    plan = validate(spec("employee_eligibility", select=["record_token", "tax_year"]), MODEL)
    assert employee_level_labels(plan) == ("record_token",)


def test_aggregations_the_model_declares_are_all_real_enum_members():
    assert {a for d in MODEL.datasets for c in d.columns for a in c.aggregations} <= set(Agg)
