"""Small-group suppression: an aggregate over people never describes a group smaller than K. [RM-01]

Runs the real capabilities over `tests/small_group_fixture.py`, a database whose worksites hold 6, 5, 3, 1
and 1 people. K is the default 5 throughout unless a test names another.
"""
from __future__ import annotations

import pytest

from application.capabilities.data_query import data_distinct_values, data_query
from application.capabilities.errors import DataQueryRefused
from application.data.build import build_query
from application.data.dialect import Dialect
from application.data.errors import GroupsAreIndividuals
from application.data.limits import QueryLimits
from application.data.semantic_model import Dataset, SemanticModel, default_model
from application.data.small_groups import (
    DEFAULT_MIN_GROUP_SIZE, MIN_GROUP_SIZE_FLOOR, SIZE_LABEL, SmallGroupReport, require_person_keys, withhold,
)
from application.data.executor import Rows
from application.data.spec import QuerySpec
from bootstrap.data_wiring import limits_from_env, set_data_query_service
from bootstrap.channel_wiring import set_writer_entitlement
from tests.data_caps_fixture import CLIENT, READER_OID, WRITER_OID, person
from tests.small_group_fixture import install

COUNT = [{"column": "*", "agg": "count", "as": "n"}]
BY_SITE = {"dataset": "onezero_matrix", "client_id": CLIENT, "select": ["worksite_id"], "measures": COUNT, "method": "min_max"}


@pytest.fixture(autouse=True)
def sized_service():
    install()
    yield
    set_data_query_service(None)
    set_writer_entitlement(None)


def rows_of(result) -> dict:
    return {r["worksite_id"]: r["n"] for r in result.facts["rows"]}


# ----------------------------------------------------------------- suppression


def test_a_group_below_k_is_left_out_and_the_ones_shown_are_exact():
    result = data_query(person(), **BY_SITE)
    assert rows_of(result) == {"W-BIG": 6, "W-EDGE": 5}, "five is enough; three, one and one are not"
    table = next(b for b in result.blocks if b.kind == "table")
    assert [r[1] for r in table.rows[1:]] == ["W-BIG", "W-EDGE"], "the method leads, then the worksite"


def test_the_result_says_how_many_groups_were_left_out_and_why():
    result = data_query(person(), **BY_SITE)
    assert result.facts["small_groups"] == {
        "min_group_size": 5, "applied": True, "suppressed_groups": 3, "exempt": None,
        "basis": "distinct people in the group",
    }
    text = " ".join(result.warnings)
    assert "3 group(s) with fewer than 5 people were left out" in text and "exact and complete" in text
    assert any("3 group(s)" in b.text for b in result.blocks if b.kind == "callout")


def test_the_suppressed_total_is_the_writers_group_count_minus_the_groups_shown():
    shown = data_query(person(), **BY_SITE).facts
    everything = data_query(person(WRITER_OID), **BY_SITE).facts
    assert len(everything["rows"]) == 5
    assert shown["small_groups"]["suppressed_groups"] == len(everything["rows"]) - len(shown["rows"])
    assert {r["worksite_id"]: r["n"] for r in shown["rows"]}.items() <= {r["worksite_id"]: r["n"] for r in everything["rows"]}.items()


def test_a_writer_sees_every_group_and_the_result_says_the_rule_was_not_applied():
    result = data_query(person(WRITER_OID), **BY_SITE)
    assert rows_of(result) == {"W-BIG": 6, "W-EDGE": 5, "W-SMALL": 3, "W-ONE": 1, "W-TWO": 1}
    assert result.facts["small_groups"]["applied"] is False and result.facts["small_groups"]["exempt"] == "writer"
    assert result.facts["small_groups"]["suppressed_groups"] == 0 and not any("left out" in w for w in result.warnings)


def test_the_rule_holds_in_every_channel_for_a_non_writer_and_a_writer_is_exempt_in_every_channel():
    for channel in ("teams", "m365-copilot", "cowork", None):
        assert set(rows_of(data_query(person(READER_OID, channel), **BY_SITE))) == {"W-BIG", "W-EDGE"}, channel
        assert len(rows_of(data_query(person(WRITER_OID, channel), **BY_SITE))) == 5, channel


def test_the_group_is_counted_in_people_not_rows():
    spec = {**BY_SITE, "dataset": "employee_period_fact", "select": ["worksite_id"]}
    spec.pop("method")
    seen = data_query(person(), **spec)
    everything = data_query(person(WRITER_OID), **spec)
    assert {r["worksite_id"]: r["n"] for r in everything.facts["rows"]}["W-SMALL"] == 12, "twelve pay periods"
    assert "W-SMALL" not in rows_of(seen), "but three people, so the group is not shown"
    assert rows_of(seen) == {"W-BIG": 6, "W-EDGE": 5}


# -------------------------------------------------- filters, derived columns, ungrouped


def test_a_filter_that_shrinks_a_group_below_k_suppresses_it():
    spec = {**BY_SITE, "filters": [{"column": "weight", "op": "gte", "value": 1}]}
    assert rows_of(data_query(person(), **BY_SITE)).get("W-BIG") == 6
    result = data_query(person(), **spec)
    assert "W-BIG" not in rows_of(result), "the filter left four full-weight people at W-BIG"
    assert result.facts["small_groups"]["suppressed_groups"] >= 1


def test_an_ungrouped_aggregate_is_one_group_and_a_small_one_is_withheld():
    small = data_query(person(), dataset="onezero_matrix", client_id=CLIENT, method="min_max", measures=COUNT,
                       filters=[{"column": "worksite_id", "op": "eq", "value": "W-SMALL"}])
    assert small.facts["rows"] == [] and small.facts["small_groups"]["suppressed_groups"] == 1
    big = data_query(person(), dataset="onezero_matrix", client_id=CLIENT, method="min_max", measures=COUNT,
                     filters=[{"column": "worksite_id", "op": "eq", "value": "W-BIG"}])
    assert [r["n"] for r in big.facts["rows"]] == [6] and big.facts["small_groups"]["suppressed_groups"] == 0


def test_an_average_over_a_filter_that_isolates_people_cannot_reveal_them():
    result = data_query(person(), dataset="employee_period_fact", client_id=CLIENT,
                        measures=[{"column": "hours", "agg": "avg", "as": "avg_hours"}],
                        filters=[{"column": "worksite_id", "op": "in", "value": ["W-ONE", "W-TWO"]}])
    assert result.facts["rows"] == [] and result.facts["small_groups"]["suppressed_groups"] == 1


def test_an_empty_match_is_not_a_suppressed_group():
    result = data_query(person(), dataset="employee_period_fact", client_id=CLIENT, measures=COUNT,
                        filters=[{"column": "worksite_id", "op": "eq", "value": "NOWHERE"}])
    assert [r["n"] for r in result.facts["rows"]] == [0] and result.facts["small_groups"]["suppressed_groups"] == 0


def test_a_derived_column_groups_by_people_too():
    result = data_query(person(), dataset="payroll", client_id=CLIENT, select=["pay_year"], measures=COUNT)
    assert [(r["pay_year"], r["n"]) for r in result.facts["rows"]] == [(2023, 6)]
    assert result.facts["small_groups"]["suppressed_groups"] == 1, "2022 holds three people"


# ------------------------------------------------------------------ singleton refusal


def test_a_grouping_where_every_group_is_one_person_is_refused():
    spec = {**BY_SITE, "filters": [{"column": "worksite_id", "op": "in", "value": ["W-ONE", "W-TWO"]}]}
    with pytest.raises(DataQueryRefused) as refused:
        data_query(person(), **spec)
    assert refused.value.code == "groups_are_individuals" and refused.value.status == 422


def test_grouping_an_aggregate_by_the_person_handle_is_refused_in_the_person_lane_as_well():
    with pytest.raises(DataQueryRefused) as refused:
        data_query(person(), dataset="onezero_matrix", client_id=CLIENT, method="min_max", select=["record_token"],
                   measures=[{"column": "weight", "agg": "sum", "as": "total_weight"}])
    assert refused.value.code == "groups_are_individuals"


def test_a_writer_may_group_down_to_single_people():
    spec = {**BY_SITE, "filters": [{"column": "worksite_id", "op": "in", "value": ["W-ONE", "W-TWO"]}]}
    assert rows_of(data_query(person(WRITER_OID), **spec)) == {"W-ONE": 1, "W-TWO": 1}


def test_mixed_group_sizes_are_not_a_singleton_grouping():
    result = data_query(person(), **{**BY_SITE, "filters": [{"column": "worksite_id", "op": "in", "value": ["W-ONE", "W-BIG"]}]})
    assert rows_of(result) == {"W-BIG": 6}


# ------------------------------------------------------------- what the rule leaves alone


def test_raw_rows_for_the_person_are_not_aggregates_and_are_not_suppressed():
    result = data_query(person(), dataset="onezero_matrix", client_id=CLIENT, method="min_max", select=["record_token"], limit=3)
    assert len(result.facts["rows"]) == 3 and "small_groups" not in result.facts and result.user_only_facts == ("rows",)


def test_a_dataset_that_is_not_about_people_is_never_suppressed():
    result = data_query(person(), dataset="unit_month_summary", client_id=CLIENT, select=["method"], measures=COUNT)
    assert result.facts["rows"] and "small_groups" not in result.facts


def test_the_model_lane_carries_the_count_of_what_was_left_out_and_no_value_of_it():
    result = data_query(person(), **BY_SITE)
    assert result.facts["audience"] == "both" and result.user_only_facts == ()
    assert "W-SMALL" not in str(result.to_dict()) and "W-ONE" not in str(result.to_dict())


def test_distinct_values_do_not_list_a_value_held_by_a_small_group():
    values = data_distinct_values(person(), CLIENT, "onezero_matrix", "worksite_id").facts
    assert {v["value"] for v in values["values"]} == {"W-BIG", "W-EDGE"} and values["small_groups"]["suppressed_groups"] == 3
    everything = data_distinct_values(person(WRITER_OID), CLIENT, "onezero_matrix", "worksite_id").facts
    assert {v["value"] for v in everything["values"]} == {"W-BIG", "W-EDGE", "W-SMALL", "W-ONE", "W-TWO"}


# ------------------------------------------------------------------------- the floor


def test_k_can_never_be_below_two():
    assert MIN_GROUP_SIZE_FLOOR == 2 and DEFAULT_MIN_GROUP_SIZE == 5
    for bad in (0, 1, -3):
        with pytest.raises(ValueError, match="never be below 2"):
            QueryLimits(min_group_size=bad)
    assert QueryLimits(min_group_size=2).min_group_size == 2


@pytest.mark.parametrize("raw, expected", [
    (None, 5), ("", 5), ("x", 5), ("8", 8), ("2", 2), ("1", 2), ("0", 2), ("-4", 2), ("100000", 1000),
])
def test_the_setting_is_clamped_to_the_floor_never_read_as_off(raw, expected):
    env = {} if raw is None else {"DATA_MIN_GROUP_SIZE": raw}
    assert limits_from_env(env).min_group_size == expected


def test_a_higher_k_withholds_more():
    install(min_group_size=6)
    assert rows_of(data_query(person(), **BY_SITE)) == {"W-BIG": 6}
    install(min_group_size=2)
    assert set(rows_of(data_query(person(), **BY_SITE))) == {"W-BIG", "W-EDGE", "W-SMALL"}


# ------------------------------------------------------------- the statement and the model


def _built(dataset: str, dialect: Dialect, **extra):
    spec = QuerySpec.from_dict({"dataset": dataset, "client_id": CLIENT, "measures": COUNT, **extra})
    return build_query(spec, default_model(), dialect, count_people=True)


def test_the_statement_counts_people_only_where_the_rule_applies():
    tsql = _built("onezero_matrix", Dialect.TSQL, select=["worksite_id"])
    assert tsql.counts_people and f"[{SIZE_LABEL}]" in tsql.sql and "COUNT(DISTINCT t.[employee_id])" in tsql.sql
    assert "{tenant" in tsql.sql.split("WHERE")[1].split("AND")[0], "the tenant marker is still the first predicate"
    summary = _built("unit_month_summary", Dialect.SQLITE, select=["method"])
    assert not summary.counts_people and SIZE_LABEL not in summary.sql
    assert not build_query(QuerySpec.from_dict({"dataset": "onezero_matrix", "client_id": CLIENT, "select": ["record_token"]}),
                           default_model(), Dialect.SQLITE, count_people=True).counts_people, "raw rows are not an aggregate"


def test_the_size_column_is_not_something_a_caller_can_ask_for():
    for dataset in default_model().datasets:
        assert dataset.column(SIZE_LABEL) is None


def test_every_employee_level_dataset_names_a_column_that_counts_its_people():
    model = default_model()
    employee_level = [d for d in model.datasets if d.employee_level]
    assert {d.name for d in employee_level} >= {"employee_period_fact", "employee_eligibility", "onezero_matrix", "payroll"}
    for dataset in employee_level:
        assert dataset.person_key and dataset.column(dataset.person_key) is not None, dataset.name
    assert all(d.person_key is None for d in model.datasets if not d.employee_level)


def test_a_model_with_an_employee_level_dataset_that_cannot_count_its_people_is_refused():
    from dataclasses import replace

    model = default_model()
    broken = replace(model.dataset("onezero_matrix"), person_key=None)
    with pytest.raises(ValueError, match="onezero_matrix"):
        require_person_keys(SemanticModel(tuple(broken if d.name == broken.name else d for d in model.datasets)))
    require_person_keys(model)


def test_withhold_unit_behaviour():
    rows = Rows(("g", "n", SIZE_LABEL), (("a", 9, 6), ("b", 2, 2), ("c", 1, 1)))
    kept, left_out = withhold(rows, 5, grouped=True)
    assert kept.columns == ("g", "n") and kept.rows == (("a", 9),) and left_out == 2
    with pytest.raises(GroupsAreIndividuals):
        withhold(Rows(("g", SIZE_LABEL), (("a", 1), ("b", 1))), 5, grouped=True)
    assert withhold(Rows(("n", SIZE_LABEL), ((1, 1),)), 5, grouped=False)[1] == 1, "an ungrouped single person is just small"
    assert withhold(Rows(("n", SIZE_LABEL), ((0, None),)), 5, grouped=False)[1] == 0, "no rows is no people"
    assert SmallGroupReport(5, True, 2).notes() and SmallGroupReport(5, True, 0).notes() == ()
