"""The audit line for a data call: what was asked, without what was found. [CH-16d]

A timeline reader needs to see that someone grouped payroll by location, or filtered on a pay
code, and which dataset it was. They do not need the result, and they must never be shown a
value that points at a person. So the line records:

- the dataset, the selected dimensions, the measures as `agg(column)`, the group-by, the years,
  the method and the limit; and
- every filter as `column op`, with the VALUE shown only where the semantic model says the column
  is a public aggregate dimension. A value on an employee-level column, on a column the model does
  not know, or on a join column is written `<redacted>`.

Names the model supplied are kept only if they are plain identifiers, so a hostile string cannot
reach a timeline through a column name. Standard library only; the gateway uses it before the
call, with the semantic model it shares with the API.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from application.data.semantic_model import Dataset, SemanticModel, Sensitivity, default_model

DATA_TOOLS = frozenset({"data_query", "data_distinct_values"})
REDACTED = "<redacted>"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.*]{0,63}$")
_SHOWN = 40
_LISTED = 5


@lru_cache(maxsize=1)
def _model() -> SemanticModel:
    """The shipped model, built once: the gateway asks on every data call."""
    return default_model()


def _name(value: Any) -> str:
    return value if value == "*" or (isinstance(value, str) and _NAME.match(value)) else "<invalid>"


def _shown(value: Any) -> str:
    items = value if isinstance(value, list) else [value]
    text = "|".join(str(i)[:_SHOWN] for i in items[:_LISTED])
    return text + ("|…" if len(items) > _LISTED else "")


def _may_show(dataset: Dataset | None, column: Any) -> bool:
    found = dataset.column(column) if dataset is not None and isinstance(column, str) else None
    return found is not None and found.queryable and found.sensitivity is Sensitivity.PUBLIC_AGGREGATE


def _filter(dataset: Dataset | None, raw: Any) -> str:
    if not isinstance(raw, Mapping):
        return "<invalid>"
    column, op = raw.get("column"), raw.get("op")
    value = _shown(raw.get("value")) if _may_show(dataset, column) else REDACTED
    return f"{_name(column)} {_name(op)} {value}"


def _measure(raw: Any) -> str:
    if not isinstance(raw, Mapping):
        return "<invalid>"
    return f"{_name(raw.get('agg'))}({_name(raw.get('column'))})"


def _each(raw: Any, one, joiner: str) -> str:
    """`one` applied to each item of a list the model supplied, or nothing for any other shape."""
    return joiner.join(one(i) for i in raw) if isinstance(raw, list) else ""


def _names(raw: Any) -> str:
    return _each(raw, _name, ",")


def _years(raw: Any) -> str:
    if isinstance(raw, Mapping):
        return f"{raw.get('from')}-{raw.get('to')}"
    return _shown(raw) if isinstance(raw, list) else ""


def _if_given(args: Mapping[str, Any], key: str, shape) -> str:
    return shape(args[key]) if key in args else ""


def summarise_data_call(tool: str, args: Mapping[str, Any]) -> dict[str, str] | None:
    """`key: text` pairs describing a data call, or None for any other tool (its own arguments are summarised as usual)."""
    if tool not in DATA_TOOLS:
        return None
    dataset = _model().dataset(args["dataset"]) if isinstance(args.get("dataset"), str) else None
    summary = {
        "dataset": _name(args.get("dataset")), "column": _if_given(args, "column", _name),
        "select": _names(args.get("select")), "group_by": _names(args.get("group_by")),
        "measures": _each(args.get("measures"), _measure, ", "),
        "filters": _each(args.get("filters"), lambda f: _filter(dataset, f), "; "),
        "years": _years(args.get("tax_years")), "method": _if_given(args, "method", _name),
        "limit": _if_given(args, "limit", lambda v: str(v)[:6]),
    }
    return {k: v for k, v in summary.items() if v}
