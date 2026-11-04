"""Typed errors for a query that was valid but could not, or must not, be run. [CH-16c]

`errors.py` says why a *specification* was refused. These say why a well-formed query did not
produce rows: it ran too long, the user is over budget, the warehouse is busy, the source is
off. They share `QueryError`'s shape (stable `code`, human message) so one handler covers both,
and none carries a database message: a driver error can quote the statement, and an error is
something that gets logged and narrated.

None of them ever comes with rows. A query that timed out returns no partial result, because a
half-read aggregate is a wrong number that looks right.
"""
from __future__ import annotations

from application.data.errors import QueryError


class QueryTimeout(QueryError):
    """The statement ran past its time limit; nothing is returned, not even the rows read so far."""

    code = "query_timeout"


class QueryBudgetExceeded(QueryError):
    """The person has used their query allowance for now; refused rather than queued."""

    code = "query_budget_exceeded"

    def __init__(self, message: str, *, retry_after_s: int, field: str | None = None) -> None:
        super().__init__(message, field=field)
        self.retry_after_s = retry_after_s


class QueryBusy(QueryError):
    """Too many data queries are already running; refused so the shared warehouse is not slowed."""

    code = "query_busy"


class DataSourceUnavailable(QueryError):
    """No connection is configured for the dataset's source in this environment."""

    code = "data_source_unavailable"


class DataSourceDisabled(QueryError):
    """The dataset's source is switched off (`DATA_QUERY_SOURCE_ENABLED`)."""

    code = "data_source_disabled"


class NotReadOnly(QueryError):
    """A statement that is not a single SELECT never reaches a cursor."""

    code = "not_read_only"


class QueryFailed(QueryError):
    """The database refused or failed the statement for a reason that is not the caller's."""

    code = "query_failed"
