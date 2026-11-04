"""A validated specification, resolved against the model: what the builder consumes. [CH-16b]

Validation does the hard thinking once (which dataset, which physical column, whether the
operator is allowed, what the value really is) and records the answers here. The SQL
builder and the audience classifier then read this and never go back to the caller's
strings, so there is exactly one place where a caller's text turns into a model fact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.data.semantic_model import Agg, Column, Dataset, JoinDecl, Op, Sensitivity

BASE_ALIAS = "t"


@dataclass(frozen=True, slots=True)
class ColumnRef:
    """A column resolved against the model: its definition, the table alias it lives on, its output label."""

    ref: str
    column: Column
    alias: str
    label: str


@dataclass(frozen=True, slots=True)
class FilterPlan:
    """A predicate on a resolved column, with its value already coerced to the column's type."""

    ref: ColumnRef
    op: Op
    value: Any


@dataclass(frozen=True, slots=True)
class MeasurePlan:
    """An aggregate over a resolved column (`ref` is None for a row count) under an output name."""

    ref: ColumnRef | None
    agg: Agg
    alias: str


@dataclass(frozen=True, slots=True)
class OrderPlan:
    """An ordering key: a selected column (`ref`) or a measure (`ref` None, `label` its alias)."""

    label: str
    direction: str
    ref: ColumnRef | None


@dataclass(frozen=True, slots=True)
class ResultColumn:
    """One column of the result, in order, with what the renderer and the lanes need to know."""

    label: str
    kind: str
    logical: str
    unit: str | None
    sensitivity: Sensitivity


@dataclass(frozen=True, slots=True)
class JoinPlan:
    """A declared join a query's columns need, with the dataset it points at."""

    decl: JoinDecl
    target: Dataset


@dataclass(frozen=True, slots=True)
class Plan:
    """Everything the builder needs, nothing it must re-check.

    `method` is the effective reading: a dataset with a method column always carries one
    (`both` when the caller did not choose), and its column is always in `select`.
    """

    dataset: Dataset
    client_id: int
    tax_years: tuple[int, ...]
    method: str | None
    select: tuple[ColumnRef, ...]
    measures: tuple[MeasurePlan, ...]
    filters: tuple[FilterPlan, ...]
    group_by: tuple[ColumnRef, ...]
    order_by: tuple[OrderPlan, ...]
    limit: int
    joins: tuple[JoinPlan, ...]

    @property
    def result_columns(self) -> tuple[ResultColumn, ...]:
        """The result's columns in SELECT order: dimensions first, then measures."""
        dims = tuple(
            ResultColumn(r.label, "dimension", r.column.logical, r.column.unit, r.column.sensitivity)
            for r in self.select
        )
        measures = tuple(
            ResultColumn(m.alias, "measure", m.ref.column.logical if m.ref else "*",
                         _measure_unit(m), m.ref.column.sensitivity if m.ref else Sensitivity.PUBLIC_AGGREGATE)
            for m in self.measures
        )
        return dims + measures


def _measure_unit(measure: MeasurePlan) -> str | None:
    """A count has no unit; the other aggregates keep the column's."""
    if measure.ref is None or measure.agg in (Agg.COUNT, Agg.COUNT_DISTINCT):
        return None
    return measure.ref.column.unit
