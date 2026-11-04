"""Validate a specification against the semantic model, and resolve it into a `Plan`. [CH-16b]

The whole of what a caller may and may not ask is decided here, in a fixed order, and the
first rule broken raises a typed error (`errors.py`). Nothing is repaired or guessed: a
column the model does not know is refused, never mapped to a near match, because a query
that quietly answers a different question is worse than one that fails.
"""
from __future__ import annotations

from collections.abc import Collection

from application.data.errors import (
    EmptyQuery, LimitTooHigh, MalformedSpec, MethodNotApplicable, MissingClient, TaxYearNotApplicable,
    TaxYearOutOfRange, UnknownDataset, ValueTypeMismatch,
)
from application.data.plan import Plan
from application.data.resolve import ColumnResolver
from application.data.semantic_model import Dataset, SemanticModel
from application.data.spec import MAX_LIMIT, METHODS, QuerySpec
from application.data.validate_columns import (
    check_caps, check_names, lead_with, plan_group_by, plan_measures, plan_order, plan_select,
)
from application.data.validate_filters import plan_filters

MIN_YEAR, MAX_YEAR = 2000, 2100


def validate(spec: QuerySpec, model: SemanticModel, *, known_years: Collection[int] | None = None) -> Plan:
    """The resolved plan for `spec`, or the typed error saying why it may not run.

    `known_years` is what the caller knows exists for this client (the runtime reads it
    from the client's scope); a year outside it is refused instead of returning nothing.
    """
    dataset = model.dataset(spec.dataset) if isinstance(spec.dataset, str) else None
    if dataset is None:
        raise UnknownDataset("no such dataset; read the catalog for the names", field="dataset")
    client_id = _client(spec)
    years = _years(spec, dataset, known_years)
    method = _method(spec, dataset)
    check_caps(spec)
    resolver = ColumnResolver(dataset, model)
    method_ref = resolver.resolve(dataset.method_column, field="method") if dataset.method_column else None
    select = plan_select(spec, resolver)
    measures = plan_measures(spec, resolver)
    if not select and not measures:
        raise EmptyQuery("select at least one column or one measure")
    select = lead_with(select, method_ref)
    group_by = plan_group_by(spec, select, measures, resolver, method_ref)
    check_names(select, measures)
    return Plan(
        dataset=dataset, client_id=client_id, tax_years=years, method=method, select=select,
        measures=measures, filters=plan_filters(spec, resolver), group_by=group_by,
        order_by=plan_order(spec, select, measures), limit=_limit(spec), joins=resolver.joins_used(),
    )


def _client(spec: QuerySpec) -> int:
    if spec.client_id is None:
        raise MissingClient("every query is scoped to one client: give client_id", field="client_id")
    if isinstance(spec.client_id, bool) or not isinstance(spec.client_id, int) or spec.client_id <= 0:
        raise MalformedSpec("client_id must be a positive integer", field="client_id")
    return spec.client_id


def _years(spec: QuerySpec, dataset: Dataset, known: Collection[int] | None) -> tuple[int, ...]:
    if not spec.tax_years:
        return ()
    if dataset.year_column is None:
        raise TaxYearNotApplicable(f"{dataset.name} has no tax year; filter its own date columns", field="tax_years")
    years = tuple(sorted(set(spec.tax_years)))
    if any(not MIN_YEAR <= y <= MAX_YEAR for y in years) or (known is not None and not set(years) <= set(known)):
        raise TaxYearOutOfRange("a tax year the client has no data for", field="tax_years")
    return years


def _method(spec: QuerySpec, dataset: Dataset) -> str | None:
    """A dataset holding both readings always answers under one named reading, `both` by default."""
    if dataset.method_column is None:
        if spec.method is not None:
            raise MethodNotApplicable(f"{dataset.name} does not hold both statutory readings", field="method")
        return None
    method = "both" if spec.method is None else spec.method
    if method not in METHODS:
        raise ValueTypeMismatch("method must be min_max, pay_period or both", field="method")
    return method


def _limit(spec: QuerySpec) -> int:
    if isinstance(spec.limit, bool) or not isinstance(spec.limit, int) or spec.limit < 1:
        raise MalformedSpec("limit must be a positive integer", field="limit")
    if spec.limit > MAX_LIMIT:
        raise LimitTooHigh(f"limit is capped at {MAX_LIMIT}", field="limit")
    return spec.limit
