"""Run a validated query specification and return a result with its provenance. [CH-16c]

`DataQueryService.run(spec, principal=...)` is the one entry the capabilities (CH-16d) call.
In order, and each step refuses rather than degrades:

1. **Build** the statement from the semantic model (validation and the tenant-first scope live
   there). A specification that may not run never reaches the budget or the warehouse.
2. **Choose the source.** A dataset's source maps to one executor; a source that is switched off
   or has no connection is a typed refusal, not a fall back to another store.
3. **Spend the person's budget**, then **take a bulkhead slot**, so a loop of queries cannot
   crowd out the portal.
4. **Execute** under the timeout and row cap, then read the run behind a live-run dataset.
5. **Withhold small groups** of an aggregate over people (`small_groups.py`), unless the caller is
   exempt, before any lane is projected from the rows.
6. **Return** rows, the lane they belong to (`audience`), the employee-level labels CH-16d must
   keep out of model-visible facts, and the provenance.

Nothing here formats a number or writes prose.
"""
from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from application.data.build import BuiltQuery, build_query
from application.data.classify import employee_level_labels, result_audience
from application.data.dialect import DEFAULT_SCHEMAS, SchemaNames
from application.data.errors import UnknownDataset
from application.data.exec_errors import DataSourceDisabled, DataSourceUnavailable, QueryBudgetExceeded
from application.data.executor import DataQueryExecutor, Rows
from application.data.limits import Bulkhead, QueryBudget, QueryLimits
from application.data.plan import ResultColumn
from application.data.provenance import QueryProvenance, build_provenance
from application.data.run_context import read_live_run
from application.data.semantic_model import Currency, Source, SemanticModel
from application.data.small_groups import SmallGroupReport, WRITER, counts_people, require_person_keys, withhold
from application.data.spec import QuerySpec
from application.data.validate import validate

YearsFor = Callable[[int], Collection[int] | None]


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Rows and everything needed to render, audit and lane them."""

    columns: tuple[ResultColumn, ...]
    rows: tuple[tuple, ...]
    audience: str
    employee_level_labels: tuple[str, ...]
    provenance: QueryProvenance

    @property
    def truncated(self) -> bool:
        """Whether more rows matched than were returned."""
        return self.provenance.truncated


class DataQueryService:
    """Composes the model, the executors and the limits into one governed read."""

    def __init__(
        self, model: SemanticModel, executors: Mapping[Source, DataQueryExecutor], *,
        limits: QueryLimits | None = None, budget: QueryBudget | None = None,
        schemas: SchemaNames = DEFAULT_SCHEMAS, disabled: Collection[Source] = (),
        years_for: YearsFor | None = None,
    ) -> None:
        require_person_keys(model)
        self._model, self._executors, self._schemas = model, dict(executors), schemas
        self._limits = limits or QueryLimits()
        self._bulkhead = Bulkhead(self._limits.max_concurrency, self._limits.busy_wait_s)
        self._budget, self._disabled, self._years_for = budget, frozenset(disabled), years_for

    def available_sources(self) -> frozenset[Source]:
        """Sources a query can run against right now: configured and not switched off."""
        return frozenset(s for s in self._executors if s not in self._disabled)

    @property
    def model(self) -> SemanticModel:
        """The semantic model this service validates against: what the catalog tool describes."""
        return self._model

    @property
    def min_group_size(self) -> int:
        """The smallest group of people an aggregate may show to a caller the rule applies to."""
        return self._limits.min_group_size

    def audience_of(self, spec: QuerySpec) -> str:
        """The lane a result for `spec` would travel in, decided before anything runs.

        Validation only: no budget is spent and no statement reaches a source, so a channel that
        may not carry person-level rows can refuse a query without having read them.
        """
        return result_audience(validate(spec, self._model))

    def run(self, spec: QuerySpec, *, principal: str, suppress_small_groups: bool = True) -> QueryResult:
        """Validate, budget, execute and describe. Raises a typed `QueryError`; never a partial result.

        `suppress_small_groups` is True unless the caller is entitled to the client's employee rows
        (a writer): the capability decides that, this only applies it, before any lane is projected.
        """
        source = self._source_of(spec)
        executor = self._executor(source)
        known = self._years_for(spec.client_id) if self._years_for and isinstance(spec.client_id, int) else None
        built = build_query(spec, self._model, executor.dialect, self._schemas, known_years=known,
                            count_people=suppress_small_groups)
        self._spend(principal)
        row_limit = self._limits.rows_for(built.plan.limit)
        with self._bulkhead.slot():
            rows = self._execute(executor, built, row_limit)
            run = self._live_run(executor, built)
        rows, report = self._small_groups(built, rows, suppress_small_groups)
        return self._result(built, rows, row_limit, run, report)

    def _small_groups(self, built: BuiltQuery, rows: Rows, suppress: bool) -> tuple[Rows, SmallGroupReport | None]:
        """Apply the minimum group size to rows that came with their group sizes; say what it did."""
        k = self._limits.min_group_size
        if not counts_people(built.plan):
            return rows, None
        if not suppress:
            return rows, SmallGroupReport(k, applied=False, exempt=WRITER)
        kept, left_out = withhold(rows, k, grouped=bool(built.plan.group_by))
        return kept, SmallGroupReport(k, applied=True, suppressed_groups=left_out)

    def _source_of(self, spec: QuerySpec) -> Source:
        dataset = self._model.dataset(spec.dataset) if isinstance(spec.dataset, str) else None
        if dataset is None:
            validate(spec, self._model)
            raise UnknownDataset("no such dataset", field="dataset")
        return dataset.source

    def _executor(self, source: Source) -> DataQueryExecutor:
        if source in self._disabled:
            raise DataSourceDisabled(f"the {source.value} data source is switched off in this environment")
        if source not in self._executors:
            raise DataSourceUnavailable(f"the {source.value} data source is not configured in this environment")
        return self._executors[source]

    def _spend(self, principal: str) -> None:
        if self._budget is None:
            return
        allowed, wait = self._budget.allow(f"data_query:{principal}")
        if not allowed:
            raise QueryBudgetExceeded("too many data queries just now; try again shortly", retry_after_s=wait)

    def _execute(self, executor: DataQueryExecutor, built: BuiltQuery, max_rows: int) -> Rows:
        return executor.execute(
            built.sql, built.params, client_id=built.plan.client_id,
            timeout_s=self._limits.timeout_s, max_rows=max_rows,
        )

    def _live_run(self, executor: DataQueryExecutor, built: BuiltQuery):
        if built.plan.dataset.currency is not Currency.LIVE_RUN:
            return None
        return read_live_run(
            built.plan.client_id, self._model, executor.dialect, self._schemas,
            lambda lookup, rows: self._execute(executor, lookup, rows),
        )

    def _result(self, built: BuiltQuery, rows: Rows, row_limit: int, run, report: SmallGroupReport | None) -> QueryResult:
        plan = built.plan
        provenance = build_provenance(
            built, self._schemas, rows, row_limit=row_limit, run=run, executed_at=datetime.now(timezone.utc),
            small_groups=report,
        )
        return QueryResult(
            columns=plan.result_columns, rows=rows.rows, audience=result_audience(plan),
            employee_level_labels=employee_level_labels(plan), provenance=provenance,
        )
