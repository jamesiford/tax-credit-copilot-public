"""The semantic model's own integrity: sensitivity decisions, currency, joins, construction. [CH-16a]"""
from __future__ import annotations

import re

import pytest

from application.data.model_dsl import Cols
from application.data.semantic_model import (
    ColType, Column, Currency, Dataset, JoinDecl, Op, Role, SchemaKey, SemanticModel, Sensitivity, Source,
    default_model,
)

MODEL = default_model()
G = Cols()
EMPLOYEE_LEVEL_DATASETS = {"employee_period_fact", "employee_eligibility", "onezero_matrix", "payroll"}
PERSON_WORDS = re.compile(r"ssn|social|email|phone|birth|dob|first_name|last_name|employee_name|street|salary_history", re.I)


def test_the_datasets_are_the_decided_set_and_four_are_employee_level():
    assert {d.name for d in MODEL.datasets} == EMPLOYEE_LEVEL_DATASETS | {
        "unit_month_summary", "run_method_summary", "run_manifest",
        "unit_year_master", "unit_credit_installment", "location", "pay_code",
    }
    assert {d.name for d in MODEL.datasets if d.employee_level} == EMPLOYEE_LEVEL_DATASETS


def test_every_employee_identifier_is_blocked_and_the_record_token_is_the_only_handle():
    for dataset in MODEL.datasets:
        for column in dataset.columns:
            if column.physical.lower() in {"employee_id", "client_employee_id", "triggered_by"}:
                assert column.sensitivity is Sensitivity.BLOCKED, (dataset.name, column.logical)
            if column.logical == "record_token":
                assert column.sensitivity is Sensitivity.EMPLOYEE_LEVEL and dataset.employee_level


def test_no_queryable_column_is_named_like_a_person_attribute():
    names = [c.logical for d in MODEL.datasets for c in d.columns if c.queryable]
    assert not [n for n in names if PERSON_WORDS.search(n)]


def test_blocked_columns_are_never_filterable_or_aggregable():
    blocked = [c for d in MODEL.datasets for c in d.columns if not c.queryable]
    assert len(blocked) >= 5
    assert all(not c.operators and not c.aggregations for c in blocked)


@pytest.mark.parametrize("dataset", MODEL.datasets, ids=lambda d: d.name)
def test_a_dataset_declares_how_its_live_rows_are_identified(dataset):
    physical = {c.physical for c in dataset.columns} | {p for p, _ in dataset.excluded_columns}
    if dataset.currency is Currency.IS_CURRENT:
        assert "is_current" in physical
    if dataset.currency is Currency.LIVE_RUN:
        assert "run_id" in physical and dataset.schema is SchemaKey.GOLD


def test_every_gold_table_with_a_run_id_and_no_is_current_is_pinned_to_the_live_run():
    for dataset in MODEL.datasets:
        has_run = dataset.column("run_id") is not None
        if dataset.source is Source.WAREHOUSE and dataset.schema is SchemaKey.GOLD and has_run:
            assert dataset.currency is not Currency.NONE, dataset.name


def test_method_datasets_carry_a_two_valued_method_column():
    with_method = [d for d in MODEL.datasets if d.method_column]
    assert {d.name for d in with_method} == {
        "employee_eligibility", "onezero_matrix", "unit_month_summary",
        "run_method_summary", "unit_year_master", "unit_credit_installment",
    }
    for dataset in with_method:
        assert dataset.column(dataset.method_column).choices == ("min_max", "pay_period")


@pytest.mark.parametrize("name", ["onezero_matrix", "unit_month_summary"])
def test_monthly_datasets_expose_twelve_month_columns(name):
    assert len(MODEL.dataset(name).month_columns) == 12


def test_joins_are_many_to_one_on_a_key_of_a_target_with_the_client_key():
    for dataset in MODEL.datasets:
        for join in dataset.joins:
            target = MODEL.dataset(join.target)
            assert target.tenant_column, join.name
            assert all(target.column(t).role is Role.IDENTIFIER for _, t in join.on), join.name


def test_derived_columns_name_what_they_depend_on_and_have_a_form_per_dialect():
    derived = [c for d in MODEL.datasets for c in d.columns if c.expression]
    assert {c.logical for c in derived} == {"pay_year", "pay_month"}
    for column in derived:
        assert all("{t}" in form for form in column.expression)


def test_contains_is_offered_only_on_free_text_dimensions():
    for dataset in MODEL.datasets:
        for column in dataset.columns:
            if Op.CONTAINS in column.operators:
                assert column.free_text and column.type is ColType.TEXT


def test_every_queryable_column_has_a_description_and_money_and_hours_carry_a_unit():
    for dataset in MODEL.datasets:
        for column in dataset.columns:
            assert column.description.strip()
            if column.logical in {"wages", "hours", "annual_credit_usd", "per_job_usd"}:
                assert column.unit


def test_a_blocked_column_cannot_be_given_an_operator_or_aggregation():
    with pytest.raises(ValueError):
        Column("x", "x", ColType.TEXT, "d", Role.IDENTIFIER, Sensitivity.BLOCKED, frozenset(), frozenset({Op.EQ}))


@pytest.mark.parametrize("bad", ["a b", "a;b", "1a", "a-b", "", "x" * 70])
def test_a_column_name_must_be_a_plain_identifier(bad):
    with pytest.raises(ValueError):
        G.dim(bad, "text", "d")


def _dataset(**changes) -> Dataset:
    base = dict(
        name="t", source=Source.WAREHOUSE, schema=SchemaKey.GOLD, table="t", grain="g", description="d",
        tenant_column="client_id", columns=(G.dim("a", "int", "d"),),
    )
    return Dataset(**{**base, **changes})


def test_a_model_refuses_dangling_references():
    with pytest.raises(ValueError):
        SemanticModel((_dataset(year_column="missing"),))
    with pytest.raises(ValueError):
        SemanticModel((_dataset(joins=(JoinDecl("j", "nowhere", (("a", "a"),)),)),))
    with pytest.raises(ValueError):
        SemanticModel((_dataset(), _dataset()))
    with pytest.raises(ValueError):
        SemanticModel((_dataset(columns=(G.dim("a", "int", "d"), G.dim("a", "int", "d"))),))
