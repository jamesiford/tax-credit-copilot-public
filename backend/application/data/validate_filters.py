"""Filters: operator allowed, value shaped for the operator and typed for the column. [CH-16b]"""
from __future__ import annotations

from typing import Any

from application.data.errors import OperatorNotAllowed, TooManyItems, ValueTypeMismatch
from application.data.plan import ColumnRef, FilterPlan
from application.data.resolve import ColumnResolver
from application.data.semantic_model import ColType, Op
from application.data.spec import MAX_FILTERS, MAX_IN_VALUES, MAX_TEXT, FilterSpec, QuerySpec
from application.data.values import coerce, has_control_characters

_FIELD = "filters"


def plan_filters(spec: QuerySpec, resolver: ColumnResolver) -> tuple[FilterPlan, ...]:
    """Every filter resolved, checked against its column's allowed operators, and coerced."""
    if len(spec.filters) > MAX_FILTERS:
        raise TooManyItems(f"at most {MAX_FILTERS} filters", field=_FIELD)
    return tuple(_plan_filter(f, resolver) for f in spec.filters)


def _plan_filter(item: FilterSpec, resolver: ColumnResolver) -> FilterPlan:
    ref = resolver.resolve(item.column, field=_FIELD)
    op = _operator(item.op)
    if op not in ref.column.operators:
        raise OperatorNotAllowed(f"{ref.column.logical} does not allow {op.value}", field=_FIELD)
    return FilterPlan(ref, op, _value(ref, op, item.value))


def _operator(name: str) -> Op:
    try:
        return Op(name)
    except ValueError:
        raise OperatorNotAllowed("unknown operator; use eq, in, between, gte, lte or contains", field=_FIELD) from None


def _value(ref: ColumnRef, op: Op, raw: Any) -> Any:
    """The coerced value: a scalar, or a tuple for `in` and `between`."""
    if op is Op.CONTAINS:
        return _contains(ref, raw)
    plain = True
    if op is Op.IN:
        items = _items(raw, 1, MAX_IN_VALUES, "a list of 1 to %d values" % MAX_IN_VALUES)
        return tuple(coerce(ref.column, v, field=_FIELD, plain=plain) for v in items)
    if op is Op.BETWEEN:
        low, high = _items(raw, 2, 2, "a list of exactly two values: [low, high]")
        pair = (coerce(ref.column, low, field=_FIELD, plain=plain), coerce(ref.column, high, field=_FIELD, plain=plain))
        if pair[0] > pair[1]:
            raise ValueTypeMismatch("between needs low <= high", field=_FIELD)
        return pair
    if isinstance(raw, tuple):
        raise ValueTypeMismatch("this operator takes a single value", field=_FIELD)
    return coerce(ref.column, raw, field=_FIELD, plain=plain)


def _items(raw: Any, low: int, high: int, expected: str) -> tuple[Any, ...]:
    if not isinstance(raw, tuple) or not low <= len(raw) <= high:
        raise ValueTypeMismatch(f"the value must be {expected}", field=_FIELD)
    return raw


def _contains(ref: ColumnRef, raw: Any) -> str:
    """A literal substring for a free-text dimension: still no control characters, still length-capped."""
    if ref.column.type is not ColType.TEXT or not ref.column.free_text:
        raise OperatorNotAllowed(f"{ref.column.logical} is not a free-text column", field=_FIELD)
    if not isinstance(raw, str) or not raw or len(raw) > MAX_TEXT or has_control_characters(raw):
        raise ValueTypeMismatch(f"the value must be a plain string of 1 to {MAX_TEXT} characters", field=_FIELD)
    return raw
