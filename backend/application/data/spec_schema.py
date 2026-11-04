"""The JSON Schema for a query specification, for the capability catalog. [CH-16b]

The descriptions here are the model's only guide to the tool, so they say what to do and
what not to: use the catalog's names, never SQL, one client, small answers. The schema is
closed (`additionalProperties: false`) because a field that is not here must not be
accepted, and it is built from the same caps `spec.py` enforces so they cannot disagree;
`tests/test_data_spec_schema.py` fails if a field is added to one and not the other.
"""
from __future__ import annotations

from typing import Any

from application.data.semantic_model import Agg, Op, SemanticModel
from application.data.spec import (
    DEFAULT_LIMIT, MAX_FILTERS, MAX_GROUP_BY, MAX_IN_VALUES, MAX_LIMIT, MAX_MEASURES, MAX_ORDER_BY, MAX_SELECT,
    MAX_YEARS, METHODS,
)

_NAME = {"type": "string", "description": "A column name exactly as the catalog lists it, or join.column."}
_SCALAR = {"type": ["string", "number", "boolean"]}


def query_spec_schema(model: SemanticModel) -> dict[str, Any]:
    """The JSON Schema (draft 2020-12) for `QuerySpec.from_dict`, with `dataset` limited to the model's names."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["dataset", "client_id"],
        "properties": {
            "dataset": {"type": "string", "enum": [d.name for d in model.datasets],
                        "description": "The dataset to query. Read the catalog first: it says what one row is."},
            "client_id": {"type": "integer", "minimum": 1, "description": "The one client the query is about."},
            "tax_years": _years(),
            "select": {"type": "array", "items": _NAME, "maxItems": MAX_SELECT,
                       "description": "Columns to return as they are. With measures, these are the grouping keys."},
            "measures": _measures(),
            "filters": _filters(),
            "group_by": {"type": "array", "items": _NAME, "maxItems": MAX_GROUP_BY,
                         "description": "Optional. Defaults to the selected columns when measures are given."},
            "order_by": _order(),
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": DEFAULT_LIMIT,
                      "description": f"Rows to return, at most {MAX_LIMIT}. Prefer aggregates to long row lists."},
            "method": {"type": "string", "enum": list(METHODS), "default": "both",
                       "description": "Where a dataset holds both statutory readings: min_max, pay_period or both."},
        },
    }


def _years() -> dict[str, Any]:
    return {
        "description": "Tax years, as a list or a from/to range; omit for every year the dataset holds.",
        "oneOf": [
            {"type": "array", "items": {"type": "integer"}, "maxItems": MAX_YEARS},
            {"type": "object", "additionalProperties": False, "required": ["from", "to"],
             "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}}},
        ],
    }


def _measures() -> dict[str, Any]:
    return {
        "type": "array", "maxItems": MAX_MEASURES,
        "description": "Aggregates to compute. Use column '*' with count for a row count.",
        "items": {
            "type": "object", "additionalProperties": False, "required": ["column", "agg"],
            "properties": {
                "column": {"type": "string", "description": "A column name, or * with count."},
                "agg": {"type": "string", "enum": [a.value for a in Agg]},
                "as": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,39}$",
                       "description": "Optional name for the result column."},
            },
        },
    }


def _filters() -> dict[str, Any]:
    return {
        "type": "array", "maxItems": MAX_FILTERS,
        "description": "Predicates, all of which must hold. Values are always data, never SQL.",
        "items": {
            "type": "object", "additionalProperties": False, "required": ["column", "op", "value"],
            "properties": {
                "column": _NAME,
                "op": {"type": "string", "enum": [o.value for o in Op],
                       "description": "in takes a list; between takes [low, high]; contains is for free-text columns only."},
                "value": {"oneOf": [_SCALAR, {"type": "array", "items": _SCALAR, "maxItems": MAX_IN_VALUES}]},
            },
        },
    }


def _order() -> dict[str, Any]:
    return {
        "type": "array", "maxItems": MAX_ORDER_BY,
        "description": "Ordering; only selected columns and measure names.",
        "items": {
            "type": "object", "additionalProperties": False, "required": ["column"],
            "properties": {"column": {"type": "string"}, "direction": {"type": "string", "enum": ["asc", "desc"]}},
        },
    }
