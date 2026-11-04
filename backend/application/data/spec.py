"""The query specification: what a model is allowed to ask, as plain frozen data. [CH-16b]

A specification is a *question*, never a statement. It names a dataset, a client, the
years, the columns to see, the measures to compute, the filters and the order; it has no
field in which SQL could be written. `validate.py` checks it against the semantic model and
`build.py` turns it into a parameterised statement, so the only text that ever reaches the
database was authored by a person and reviewed.

Standard library only. `from_dict` is the single entry from untrusted JSON: it enforces
the *shape* (known keys, right types) and leaves the *meaning* (does that column exist, may
it be filtered) to validation, which knows the model.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from application.data.errors import MalformedSpec

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_FILTERS = 8
MAX_MEASURES = 6
MAX_SELECT = 12
MAX_GROUP_BY = 8
MAX_ORDER_BY = 4
MAX_IN_VALUES = 50
MAX_YEARS = 12
MAX_TEXT = 100
METHODS = ("min_max", "pay_period", "both")

_TOP_KEYS = frozenset({
    "dataset", "client_id", "tax_years", "select", "measures", "filters",
    "group_by", "order_by", "limit", "method",
})


@dataclass(frozen=True, slots=True)
class MeasureSpec:
    """One aggregate: `agg` of `column` (or `*` for a row count), optionally named `alias`."""

    column: str
    agg: str
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """One predicate. `value` is a scalar, or a tuple for `in` (any length) and `between` (two)."""

    column: str
    op: str
    value: Any


@dataclass(frozen=True, slots=True)
class OrderSpec:
    """One ordering key: a selected column or a measure alias."""

    column: str
    direction: str = "asc"


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """A structured, read-only question. `limit` defaults to 100 and never exceeds 500."""

    dataset: str
    client_id: int | None
    tax_years: tuple[int, ...] = ()
    select: tuple[str, ...] = ()
    measures: tuple[MeasureSpec, ...] = ()
    filters: tuple[FilterSpec, ...] = ()
    group_by: tuple[str, ...] = ()
    order_by: tuple[OrderSpec, ...] = ()
    limit: int = DEFAULT_LIMIT
    method: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QuerySpec:
        """Build a specification from decoded JSON, refusing anything that is not its shape."""
        if not isinstance(payload, Mapping):
            raise MalformedSpec("the query must be a JSON object")
        extra = set(payload) - _TOP_KEYS
        if extra:
            raise MalformedSpec("unknown field(s): " + ", ".join(sorted(map(str, extra))), field=None)
        return cls(
            dataset=_text(payload, "dataset"),
            client_id=_client(payload.get("client_id")),
            tax_years=_years(payload.get("tax_years")),
            select=_texts(payload, "select"),
            measures=tuple(_measure(m) for m in _items(payload, "measures")),
            filters=tuple(_filter(f) for f in _items(payload, "filters")),
            group_by=_texts(payload, "group_by"),
            order_by=tuple(_order(o) for o in _items(payload, "order_by")),
            limit=_limit(payload.get("limit")),
            method=_optional_text(payload, "method"),
        )

    def to_dict(self) -> dict[str, Any]:
        """The JSON form, for provenance and for the round trip the tests rely on."""
        return {
            "dataset": self.dataset, "client_id": self.client_id, "tax_years": list(self.tax_years),
            "select": list(self.select),
            "measures": [{"column": m.column, "agg": m.agg, "as": m.alias} for m in self.measures],
            "filters": [{"column": f.column, "op": f.op, "value": list(f.value) if isinstance(f.value, tuple) else f.value}
                        for f in self.filters],
            "group_by": list(self.group_by),
            "order_by": [{"column": o.column, "direction": o.direction} for o in self.order_by],
            "limit": self.limit, "method": self.method,
        }


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise MalformedSpec(f"{key} must be a non-empty string", field=key)
    return value


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise MalformedSpec(f"{key} must be a string", field=key)
    return value


def _items(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise MalformedSpec(f"{key} must be a list", field=key)
    return value


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    items = _items(payload, key)
    if not all(isinstance(i, str) for i in items):
        raise MalformedSpec(f"{key} must be a list of strings", field=key)
    return tuple(items)


def _client(value: Any) -> int | None:
    if value is None:
        return None
    if not _is_int(value):
        raise MalformedSpec("client_id must be an integer", field="client_id")
    return value


def _limit(value: Any) -> int:
    if value is None:
        return DEFAULT_LIMIT
    if not _is_int(value):
        raise MalformedSpec("limit must be an integer", field="limit")
    return value


def _years(value: Any) -> tuple[int, ...]:
    """A list of years, or `{"from": a, "to": b}` expanded; at most `MAX_YEARS`."""
    if value is None:
        return ()
    if isinstance(value, Mapping):
        if set(value) != {"from", "to"} or not (_is_int(value["from"]) and _is_int(value["to"])):
            raise MalformedSpec("tax_years as a range needs integer from and to", field="tax_years")
        lo, hi = value["from"], value["to"]
        if not 0 <= hi - lo < MAX_YEARS:
            raise MalformedSpec(f"a tax-year range must span 1 to {MAX_YEARS} years", field="tax_years")
        return tuple(range(lo, hi + 1))
    return _year_list(value)


def _year_list(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(_is_int(y) for y in value):
        raise MalformedSpec("tax_years must be a list of integers or a from/to range", field="tax_years")
    if len(value) > MAX_YEARS:
        raise MalformedSpec(f"at most {MAX_YEARS} tax years", field="tax_years")
    return tuple(value)


def _measure(raw: Any) -> MeasureSpec:
    if not isinstance(raw, Mapping) or not set(raw) <= {"column", "agg", "as"} or not {"column", "agg"} <= set(raw):
        raise MalformedSpec("a measure is {column, agg, as?}", field="measures")
    alias = raw.get("as")
    if not isinstance(raw["column"], str) or not isinstance(raw["agg"], str) or not (alias is None or isinstance(alias, str)):
        raise MalformedSpec("a measure's column, agg and as must be strings", field="measures")
    return MeasureSpec(raw["column"], raw["agg"], alias)


def _filter(raw: Any) -> FilterSpec:
    if not isinstance(raw, Mapping) or set(raw) != {"column", "op", "value"}:
        raise MalformedSpec("a filter is {column, op, value}", field="filters")
    if not isinstance(raw["column"], str) or not isinstance(raw["op"], str):
        raise MalformedSpec("a filter's column and op must be strings", field="filters")
    value = tuple(raw["value"]) if isinstance(raw["value"], list) else raw["value"]
    items = value if isinstance(value, tuple) else (value,)
    if not all(isinstance(v, (str, int, float, bool)) for v in items):
        raise MalformedSpec("a filter value must be a string, number, boolean or a list of them", field="filters")
    return FilterSpec(raw["column"], raw["op"], value)


def _order(raw: Any) -> OrderSpec:
    if isinstance(raw, str):
        return OrderSpec(raw)
    if not isinstance(raw, Mapping) or not set(raw) <= {"column", "direction"} or not isinstance(raw.get("column"), str):
        raise MalformedSpec("an ordering is a column name or {column, direction?}", field="order_by")
    direction = raw.get("direction", "asc")
    if direction not in ("asc", "desc"):
        raise MalformedSpec("direction must be asc or desc", field="order_by")
    return OrderSpec(raw["column"], direction)
