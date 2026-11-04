"""Columns: what is selected, aggregated, grouped and ordered. [CH-16b]"""
from __future__ import annotations

import re

from application.data.errors import (
    AggregationNotAllowed, DuplicateName, GroupByMeasure, InvalidAlias, OrderByOutsideSelection,
    SelectNotGrouped, TooManyItems,
)
from application.data.plan import ColumnRef, MeasurePlan, OrderPlan
from application.data.resolve import ColumnResolver
from application.data.semantic_model import Agg, Role
from application.data.spec import MAX_GROUP_BY, MAX_MEASURES, MAX_ORDER_BY, MAX_SELECT, QuerySpec

_ALIAS = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
ROW_COUNT = "*"


def check_caps(spec: QuerySpec) -> None:
    """Small, fixed caps: a query is a question, not a report."""
    for name, items, cap in (
        ("select", spec.select, MAX_SELECT), ("measures", spec.measures, MAX_MEASURES),
        ("group_by", spec.group_by, MAX_GROUP_BY), ("order_by", spec.order_by, MAX_ORDER_BY),
    ):
        if len(items) > cap:
            raise TooManyItems(f"at most {cap} entries in {name}", field=name)


def plan_select(spec: QuerySpec, resolver: ColumnResolver) -> tuple[ColumnRef, ...]:
    """The selected columns, resolved; the same column twice is refused."""
    refs = tuple(resolver.resolve(c, field="select") for c in spec.select)
    return refs


def plan_measures(spec: QuerySpec, resolver: ColumnResolver) -> tuple[MeasurePlan, ...]:
    """Each aggregate checked against the column's allowed aggregations and given a plain alias."""
    plans = []
    for item in spec.measures:
        agg = _agg(item.agg)
        ref = None
        if item.column == ROW_COUNT:
            if agg is not Agg.COUNT:
                raise AggregationNotAllowed("* may only be counted", field="measures")
        else:
            ref = resolver.resolve(item.column, field="measures")
            if agg not in ref.column.aggregations:
                raise AggregationNotAllowed(f"{ref.column.logical} does not allow {agg.value}", field="measures")
        plans.append(MeasurePlan(ref, agg, _alias(item.alias, agg, ref)))
    return tuple(plans)


def _agg(name: str) -> Agg:
    try:
        return Agg(name)
    except ValueError:
        raise AggregationNotAllowed("unknown aggregation; use count, count_distinct, sum, avg, min or max",
                                    field="measures") from None


def _alias(alias: str | None, agg: Agg, ref: ColumnRef | None) -> str:
    if alias is None:
        return f"{agg.value}_{ref.label}" if ref else "row_count"
    if not _ALIAS.match(alias):
        raise InvalidAlias("an alias is lowercase letters, digits and underscores, starting with a letter, 40 at most",
                           field="measures")
    return alias


def plan_group_by(spec: QuerySpec, select: tuple[ColumnRef, ...], measures: tuple[MeasurePlan, ...],
                  resolver: ColumnResolver, auto: ColumnRef | None = None) -> tuple[ColumnRef, ...]:
    """The grouping keys. With aggregates, grouping defaults to the selection and must cover it.

    `auto` is the method column of a dataset holding both readings: it is always selected, so
    it is always grouped, even when the caller listed explicit keys.
    """
    explicit = _explicit_keys(spec, resolver, auto)
    keys = explicit or (select if measures else ())
    if measures:
        _check_covered(select, keys)
    elif explicit and {k.label for k in explicit} != {r.label for r in select}:
        raise SelectNotGrouped("without measures, group_by must equal the selected columns", field="group_by")
    return keys


def _explicit_keys(spec: QuerySpec, resolver: ColumnResolver, auto: ColumnRef | None) -> tuple[ColumnRef, ...]:
    """The caller's grouping keys, never a measure, with the method column in front when any are given."""
    explicit = tuple(resolver.resolve(c, field="group_by") for c in spec.group_by)
    for ref in explicit:
        if ref.column.role is Role.MEASURE:
            raise GroupByMeasure(f"{ref.column.logical} is a measure and cannot be grouped by", field="group_by")
    return lead_with(explicit, auto) if explicit else explicit


def _check_covered(select: tuple[ColumnRef, ...], keys: tuple[ColumnRef, ...]) -> None:
    """With aggregates, every selected column must be a grouping key, and none may be a measure."""
    grouped = {k.label for k in keys}
    for ref in select:
        if ref.column.role is Role.MEASURE:
            raise GroupByMeasure(f"{ref.column.logical} is a measure; aggregate it instead of selecting it",
                                 field="select")
        if ref.label not in grouped:
            raise SelectNotGrouped(f"{ref.column.logical} is selected but not grouped", field="group_by")


def lead_with(refs: tuple[ColumnRef, ...], first: ColumnRef | None) -> tuple[ColumnRef, ...]:
    """`refs` with `first` in front unless it is already there: no answer without its method."""
    if first is None or any(r.label == first.label for r in refs):
        return refs
    return (first, *refs)


def check_names(select: tuple[ColumnRef, ...], measures: tuple[MeasurePlan, ...]) -> None:
    """Every output column needs its own name."""
    names = [r.label for r in select] + [m.alias for m in measures]
    if len(set(names)) != len(names):
        raise DuplicateName("two output columns would share a name; give a measure an alias", field="measures")


def plan_order(spec: QuerySpec, select: tuple[ColumnRef, ...], measures: tuple[MeasurePlan, ...]) -> tuple[OrderPlan, ...]:
    """Orderings may name only what is in the result: a selected column or a measure."""
    by_ref = {name: ref for ref in select for name in (ref.ref, ref.label)}
    aliases = {m.alias for m in measures}
    plans = []
    for item in spec.order_by:
        if item.column in by_ref:
            plans.append(OrderPlan(by_ref[item.column].label, item.direction, by_ref[item.column]))
        elif item.column in aliases:
            plans.append(OrderPlan(item.column, item.direction, None))
        else:
            raise OrderByOutsideSelection("order_by may name only a selected column or a measure", field="order_by")
    return tuple(plans)
