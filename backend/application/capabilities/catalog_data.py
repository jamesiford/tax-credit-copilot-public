"""The three data tools' contract: catalog, query and distinct values. [CH-16d]

Pure data, standard library only, vendored into the orchestrator with the rest of the catalog.
The descriptions here are the model's ONLY guide to these tools, so they say when NOT to use
them as plainly as when to: the fixed engine tools are authoritative for the credit, eligibility
and what the engine concluded; these return exact rows and aggregates and interpret nothing.

The `data_query` schema is the specification's JSON Schema, written out. It cannot import it:
a vendored catalog module may use only the standard library and its siblings, and the
specification lives with the semantic model. `tests/test_data_catalog_contract.py` fails if this
copy and `application.data.spec_schema.query_spec_schema(default_model())` ever differ, so the
caps and the dataset names cannot drift apart.
"""
from __future__ import annotations

from application.capabilities.catalog_types import READ, CapabilitySpec, _object

#: Tools whose RESULT describes the shape of the data (names, units, the values a dimension can
#: take), never its content. A model is shown these facts themselves, because it needs them to
#: write a valid query; every other tool's facts reach it as names only.
LOOKUP = "lookup"

DATASETS = (
    "employee_period_fact", "employee_eligibility", "onezero_matrix", "unit_month_summary", "run_method_summary",
    "run_manifest", "unit_year_master", "unit_credit_installment", "payroll", "location", "pay_code",
)
DATA_METHODS = ("min_max", "pay_period", "both")
_AGGS = ("count", "count_distinct", "sum", "avg", "min", "max")
_OPS = ("eq", "in", "between", "gte", "lte", "contains")

_NAME = {"type": "string", "description": "A column name exactly as the catalog lists it, or join.column."}
_SCALAR = {"type": ["string", "number", "boolean"]}
_CLIENT = {"type": "integer", "minimum": 1, "description": "The one client the query is about."}
_YEARS = {
    "description": "Tax years, as a list or a from/to range; omit for every year the dataset holds.",
    "oneOf": [
        {"type": "array", "items": {"type": "integer"}, "maxItems": 12},
        {"type": "object", "additionalProperties": False, "required": ["from", "to"],
         "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}}},
    ],
}
_DATASET_HELP = "The dataset to query. Read the catalog first: it says what one row is."


_MEASURES = {
    "type": "array", "maxItems": 6,
    "description": "Aggregates to compute. Use column '*' with count for a row count.",
    "items": {
        "type": "object", "additionalProperties": False, "required": ["column", "agg"],
        "properties": {
            "column": {"type": "string", "description": "A column name, or * with count."},
            "agg": {"type": "string", "enum": list(_AGGS)},
            "as": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,39}$", "description": "Optional name for the result column."},
        },
    },
}
_FILTERS = {
    "type": "array", "maxItems": 8,
    "description": "Predicates, all of which must hold. Values are always data, never SQL.",
    "items": {
        "type": "object", "additionalProperties": False, "required": ["column", "op", "value"],
        "properties": {
            "column": _NAME,
            "op": {"type": "string", "enum": list(_OPS),
                   "description": "in takes a list; between takes [low, high]; contains is for free-text columns only."},
            "value": {"oneOf": [_SCALAR, {"type": "array", "items": _SCALAR, "maxItems": 50}]},
        },
    },
}
_ORDER = {
    "type": "array", "maxItems": 4, "description": "Ordering; only selected columns and measure names.",
    "items": {
        "type": "object", "additionalProperties": False, "required": ["column"],
        "properties": {"column": {"type": "string"}, "direction": {"type": "string", "enum": ["asc", "desc"]}},
    },
}


def _query_properties() -> dict:
    return {
        "dataset": {"type": "string", "enum": list(DATASETS), "description": _DATASET_HELP},
        "client_id": _CLIENT,
        "tax_years": _YEARS,
        "select": {"type": "array", "items": _NAME, "maxItems": 12,
                   "description": "Columns to return as they are. With measures, these are the grouping keys."},
        "measures": _MEASURES,
        "filters": _FILTERS,
        "group_by": {"type": "array", "items": _NAME, "maxItems": 8,
                     "description": "Optional. Defaults to the selected columns when measures are given."},
        "order_by": _ORDER,
        "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100,
                  "description": "Rows to return, at most 500. Prefer aggregates to long row lists."},
        "method": {"type": "string", "enum": list(DATA_METHODS), "default": "both",
                   "description": "Where a dataset holds both statutory readings: min_max, pay_period or both."},
    }


DATA_QUERY_DESCRIPTION = (
    "Structured, read-only query over ONE client's payroll and enriched calculation data (needs a client). "
    "Use it only for questions the fixed tools (client_eligibility, client_trend, client_at_risk, simulate and "
    "the rest) cannot answer: descriptive or comparative questions such as an average, a count or a total by "
    "location, month, year, designation or method. For anything about the credit figure, eligibility or what the "
    "engine concluded, the fixed tools are authoritative; this tool returns exact rows and aggregates from the "
    "data, it does not interpret them. Read data_catalog first and use its names exactly, never an invented "
    "column; use data_distinct_values to find a location or code before filtering on it. Name every measure with "
    "`as` (for example `average_headcount`): the answer refers to a result column by that name. Never write SQL. "
    "Prefer an aggregate to a long list: a result is capped (default 100 rows, at most 500) and says when it was "
    "cut. Rows that describe individual employees go to the person asking only; Copilot Cowork refuses them "
    "unless the user is a writer."
)

DATA_TOOLS: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        name="data_catalog",
        description=(
            "What data can be queried: datasets (what one row is), and with `dataset` their columns with "
            "meaning, unit, role, sensitivity and the aggregations and filters each allows. `search` narrows by "
            "a word in a name or description. Holds no values from the data. Needs no client. Call it before "
            "data_query, and never invent a column name: if the catalog has no column for the question, say so."
        ),
        kind=READ, needs_client=False, needs_year=False, tags=(LOOKUP,),
        schema=_object({
            "dataset": {"type": "string", "enum": list(DATASETS), "description": "One dataset's full column list."},
            "search": {"type": "string", "minLength": 2, "maxLength": 60, "description": "A word to find in names and descriptions."},
        }),
    ),
    CapabilitySpec(
        name="data_query", description=DATA_QUERY_DESCRIPTION, kind=READ, needs_client=True, needs_year=False,
        sensitive=True, schema=_object(_query_properties(), ("dataset", "client_id")),
    ),
    CapabilitySpec(
        name="data_distinct_values",
        description=(
            "The distinct values (with how many rows carry each) of ONE dimension column for a client, for "
            "example locations, designations or pay codes. Use it to resolve a name the reader gave (a location, "
            "a designation) to the value the data holds before filtering on it, never to guess one. "
            "Refuses a column whose values describe individual people. Capped; says when it was."
        ),
        kind=READ, needs_client=True, needs_year=False, tags=(LOOKUP,),
        schema=_object({
            "client_id": _CLIENT,
            "dataset": {"type": "string", "enum": list(DATASETS), "description": _DATASET_HELP},
            "column": {"type": "string", "description": "A dimension column, exactly as the catalog lists it."},
            "tax_years": _YEARS,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50,
                      "description": "Values to return, at most 100."},
        }, ("client_id", "dataset", "column")),
    ),
)
