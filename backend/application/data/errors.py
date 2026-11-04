"""Typed errors for a rejected query specification. [CH-16b]

A model that asked a malformed question needs to be told precisely why, in words it can
act on, and the caller needs a stable `code` to branch on. So each way a specification
can be wrong is its own class, and none of them echoes a value the caller supplied: a
rejected string may be hostile, and an error is something that gets logged and narrated.
"""
from __future__ import annotations


class QueryError(ValueError):
    """Base: a specification the platform refuses to run. `field` says which part."""

    code = "invalid_query"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def to_dict(self) -> dict[str, str | None]:
        """The shape a tool result carries: stable code, human message, offending field."""
        return {"code": self.code, "message": self.message, "field": self.field}


class MalformedSpec(QueryError):
    """The payload is not shaped like a query specification at all."""

    code = "malformed_spec"


class UnknownDataset(QueryError):
    """The dataset is not in the semantic model."""

    code = "unknown_dataset"


class UnknownColumn(QueryError):
    """The column is not in the dataset (or names a join that is not declared)."""

    code = "unknown_column"


class BlockedColumn(QueryError):
    """The column exists and may never be selected, filtered or grouped."""

    code = "blocked_column"


class OperatorNotAllowed(QueryError):
    """The filter operator is not allowed on this column."""

    code = "operator_not_allowed"


class AggregationNotAllowed(QueryError):
    """The aggregation is not allowed on this column."""

    code = "aggregation_not_allowed"


class GroupByMeasure(QueryError):
    """A measure cannot be a grouping key."""

    code = "group_by_measure"


class SelectNotGrouped(QueryError):
    """With aggregates, every selected column must be grouped."""

    code = "select_not_grouped"


class OrderByOutsideSelection(QueryError):
    """An ordering may only name a selected column or a measure."""

    code = "order_by_outside_selection"


class LimitTooHigh(QueryError):
    """The row limit is above the cap."""

    code = "limit_too_high"


class MissingClient(QueryError):
    """Every query is scoped to one client; none was given."""

    code = "missing_client"


class TaxYearOutOfRange(QueryError):
    """A tax year the client has no data for, or that is not a plausible year."""

    code = "tax_year_out_of_range"


class TaxYearNotApplicable(QueryError):
    """The dataset has no tax year; filter its own date columns instead."""

    code = "tax_year_not_applicable"


class MethodNotApplicable(QueryError):
    """The dataset does not hold both statutory readings, so a method makes no sense."""

    code = "method_not_applicable"


class EmptyQuery(QueryError):
    """Nothing was selected and no measure was asked for."""

    code = "empty_query"


class ValueTypeMismatch(QueryError):
    """A filter value has the wrong type or shape for its column and operator."""

    code = "value_type_mismatch"


class ValueNotAllowed(QueryError):
    """A filter value is not one of the column's declared values."""

    code = "value_not_allowed"


class SqlLikeValue(QueryError):
    """A value that looks like SQL where only a plain value belongs."""

    code = "sql_like_value"


class TooManyItems(QueryError):
    """More filters, measures, columns or values than a single query may carry."""

    code = "too_many_items"


class InvalidAlias(QueryError):
    """A measure alias that is not a plain lowercase identifier."""

    code = "invalid_alias"


class DuplicateName(QueryError):
    """Two output columns would carry the same name."""

    code = "duplicate_name"


class GroupsAreIndividuals(QueryError):
    """Every group in the result holds one person, so the grouping lists individuals rather than describing a group."""

    code = "groups_are_individuals"
