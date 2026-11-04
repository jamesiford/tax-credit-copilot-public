"""The query specification: shape, round trip, and the JSON Schema that describes it. [CH-16b]"""
from __future__ import annotations

import dataclasses

import jsonschema
import pytest

from application.data.errors import MalformedSpec
from application.data.semantic_model import default_model
from application.data.spec import DEFAULT_LIMIT, MAX_LIMIT, FilterSpec, MeasureSpec, OrderSpec, QuerySpec
from application.data.spec_schema import query_spec_schema

MODEL = default_model()
FULL = {
    "dataset": "unit_year_master", "client_id": 1001, "tax_years": [2023, 2024],
    "select": ["worksite_id"], "measures": [{"column": "annual_credit_usd", "agg": "sum", "as": "credit"}],
    "filters": [{"column": "status", "op": "in", "value": ["above_minimum", "base"]},
                {"column": "average_headcount", "op": "between", "value": [1, 9.5]}],
    "group_by": ["worksite_id"], "order_by": [{"column": "credit", "direction": "desc"}], "limit": 50, "method": "min_max",
}


def test_a_full_specification_round_trips_and_is_frozen():
    spec = QuerySpec.from_dict(FULL)
    assert spec.to_dict() == FULL
    assert isinstance(spec.measures[0], MeasureSpec) and isinstance(spec.filters[0], FilterSpec)
    assert isinstance(spec.order_by[0], OrderSpec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.limit = 1


def test_defaults_are_a_limit_of_one_hundred_and_no_method():
    spec = QuerySpec.from_dict({"dataset": "payroll", "client_id": 1})
    assert (spec.limit, spec.method, spec.tax_years, spec.select) == (DEFAULT_LIMIT, None, (), ())
    assert DEFAULT_LIMIT == 100 and MAX_LIMIT == 500


def test_a_year_range_expands_and_is_capped():
    spec = QuerySpec.from_dict({"dataset": "x", "client_id": 1, "tax_years": {"from": 2021, "to": 2023}})
    assert spec.tax_years == (2021, 2022, 2023)
    for bad in ({"from": 2000, "to": 2100}, {"from": 2023, "to": 2021}, {"from": "a", "to": 1}, {"from": 1}):
        with pytest.raises(MalformedSpec):
            QuerySpec.from_dict({"dataset": "x", "client_id": 1, "tax_years": bad})


@pytest.mark.parametrize("payload", [
    "select *", ["dataset"], {"client_id": 1}, {"dataset": "x", "client_id": "1"}, {"dataset": "x", "client_id": True},
    {"dataset": "x", "client_id": 1, "sql": "select 1"}, {"dataset": "x", "client_id": 1, "limit": "5"},
    {"dataset": "x", "client_id": 1, "select": "a"}, {"dataset": "x", "client_id": 1, "select": [1]},
    {"dataset": "x", "client_id": 1, "measures": [{"column": "a"}]},
    {"dataset": "x", "client_id": 1, "measures": [{"column": "a", "agg": "sum", "extra": 1}]},
    {"dataset": "x", "client_id": 1, "filters": [{"column": "a", "op": "eq"}]},
    {"dataset": "x", "client_id": 1, "filters": [{"column": "a", "op": "eq", "value": {"$ne": 1}}]},
    {"dataset": "x", "client_id": 1, "filters": [{"column": "a", "op": "in", "value": [[1]]}]},
    {"dataset": "x", "client_id": 1, "order_by": [{"column": "a", "direction": "sideways"}]},
    {"dataset": "x", "client_id": 1, "tax_years": ["2023"]}, {"dataset": "x", "client_id": 1, "method": 1},
])
def test_a_payload_that_is_not_the_shape_is_malformed(payload):
    with pytest.raises(MalformedSpec):
        QuerySpec.from_dict(payload)


def test_a_missing_client_is_representable_so_validation_can_name_it():
    assert QuerySpec.from_dict({"dataset": "payroll"}).client_id is None


def test_an_ordering_may_be_a_bare_column_name():
    spec = QuerySpec.from_dict({"dataset": "x", "client_id": 1, "order_by": ["a"]})
    assert spec.order_by == (OrderSpec("a", "asc"),)


def test_the_json_schema_is_valid_and_accepts_the_full_example_and_refuses_extras():
    schema = query_spec_schema(MODEL)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(FULL, schema)
    jsonschema.validate({"dataset": "payroll", "client_id": 1, "tax_years": {"from": 2021, "to": 2022}}, schema)
    for bad in ({**FULL, "sql": "select 1"}, {**FULL, "dataset": "nope"}, {**FULL, "limit": MAX_LIMIT + 1},
                {**FULL, "method": "neither"}, {k: v for k, v in FULL.items() if k != "client_id"},
                {**FULL, "measures": [{"column": "a", "agg": "median"}]}, {**FULL, "filters": [{"column": "a", "op": "like", "value": 1}]}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


def test_the_schema_properties_are_exactly_the_specification_fields():
    schema = query_spec_schema(MODEL)
    assert set(schema["properties"]) == {f.name for f in dataclasses.fields(QuerySpec)}
    assert schema["additionalProperties"] is False and set(schema["required"]) == {"dataset", "client_id"}
    assert schema["properties"]["dataset"]["enum"] == [d.name for d in MODEL.datasets]


def test_the_schema_describes_every_part_for_a_model_that_reads_nothing_else():
    schema = query_spec_schema(MODEL)
    assert all(p.get("description") for p in schema["properties"].values())
    assert "never SQL" in schema["properties"]["filters"]["description"]
