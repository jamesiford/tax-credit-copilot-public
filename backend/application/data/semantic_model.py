"""The semantic model: what the agent may ask of the data, in one reviewed place. [CH-16a]

The product's invariant is *agents narrate, tools calculate*, so a language model never
writes SQL. What it may do is fill in a structured specification (`spec.py`), and the
specification is checked against THIS model: a dataset, its grain, its columns, what each
column means, how sensitive it is and which questions it can honestly answer. Whatever
is not in here cannot be asked, and a column in here that is `blocked` can never be
selected, filtered or grouped.

Three ideas carry the design:

- **Sensitivity describes the raw value.** `employee_level` means one person's pay or
  hours; an aggregate over a group is `public_aggregate`. A query that returns raw
  employee-level values is delivered to the person and never shown to a model
  (`classify.py`).
- **Currency is part of the dataset.** Gold keeps superseded runs. A dataset says how the
  live rows are identified (`is_current`, or the client's live run), so a query can never
  mix a restated figure with the one that was filed.
- **Identifiers are tokens.** An employee appears only as a `record_token`. The tokenised
  and source employee ids are modelled as `blocked`, which is a *decision*, not an omission.

Pure data plus validation; the data lives in `model_*.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class Source(str, Enum):
    """Where a dataset physically lives."""

    WAREHOUSE = "warehouse"
    LAKEHOUSE = "lakehouse"


class SchemaKey(str, Enum):
    """Logical schema; the deployed schema name is configuration (`SchemaNames`)."""

    GOLD = "gold"
    OPS = "ops"
    SOURCE = "source"


class ColType(str, Enum):
    """Value types a filter value is checked against."""

    INT = "int"
    DECIMAL = "decimal"
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"
    BOOL = "bool"


class Role(str, Enum):
    """What a column is for in a question."""

    DIMENSION = "dimension"
    MEASURE = "measure"
    IDENTIFIER = "identifier"
    FLAG = "flag"


class Sensitivity(str, Enum):
    """How exposed a raw value is. Aggregating lowers it; `blocked` never does."""

    PUBLIC_AGGREGATE = "public_aggregate"
    EMPLOYEE_LEVEL = "employee_level"
    BLOCKED = "blocked"


class Agg(str, Enum):
    """Aggregations a column may take."""

    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class Op(str, Enum):
    """Filter operators a column may take."""

    EQ = "eq"
    IN = "in"
    BETWEEN = "between"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"


class Currency(str, Enum):
    """How a dataset's live rows are identified."""

    NONE = "none"
    IS_CURRENT = "is_current"
    LIVE_RUN = "live_run"


@dataclass(frozen=True, slots=True)
class Column:
    """One column: its logical and physical names, meaning, role, sensitivity and limits.

    `operators` empty means the column is selectable but not filterable (provenance
    columns such as `run_id`). `expression` is a (T-SQL, SQLite) template over `{t}` for
    a derived column, whose `depends_on` physical columns are what the drift test checks.
    """

    logical: str
    physical: str
    type: ColType
    description: str
    role: Role
    sensitivity: Sensitivity
    aggregations: frozenset[Agg]
    operators: frozenset[Op]
    unit: str | None = None
    choices: tuple[str, ...] = ()
    free_text: bool = False
    expression: tuple[str, str] | None = None
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (self.logical, self.physical):
            if not IDENTIFIER.match(name):
                raise ValueError(f"not a plain identifier: {name!r}")
        if not self.description.strip():
            raise ValueError(f"{self.logical}: a column needs a description")
        if self.sensitivity is Sensitivity.BLOCKED and (self.aggregations or self.operators):
            raise ValueError(f"{self.logical}: a blocked column takes no aggregation or operator")
        if self.expression is not None and not self.depends_on:
            raise ValueError(f"{self.logical}: a derived column must name what it depends on")

    @property
    def queryable(self) -> bool:
        """False for a blocked column: it is never selected, filtered or grouped."""
        return self.sensitivity is not Sensitivity.BLOCKED


@dataclass(frozen=True, slots=True)
class JoinDecl:
    """A declared fixed join to a dataset that shares the client key and is unique on `on`.

    Only many-to-one joins are declared, so a join can never multiply the base rows.
    """

    name: str
    target: str
    on: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Dataset:
    """One queryable table: grain, tenant column, time columns, currency, columns."""

    name: str
    source: Source
    schema: SchemaKey
    table: str
    grain: str
    description: str
    tenant_column: str
    columns: tuple[Column, ...]
    currency: Currency = Currency.NONE
    employee_level: bool = False
    year_column: str | None = None
    month_columns: tuple[str, ...] = ()
    period_columns: tuple[str, ...] = ()
    method_column: str | None = None
    joins: tuple[JoinDecl, ...] = ()
    engine_notes: tuple[tuple[str, str], ...] = ()
    excluded_columns: tuple[tuple[str, str], ...] = ()

    def column(self, logical: str) -> Column | None:
        """The modelled column with this logical name, blocked ones included."""
        return next((c for c in self.columns if c.logical == logical), None)

    def join(self, name: str) -> JoinDecl | None:
        """The declared join with this name."""
        return next((j for j in self.joins if j.name == name), None)

    def physical_columns(self) -> set[str]:
        """Every physical column this dataset accounts for, for the drift test."""
        columns = {c.physical for c in self.columns if c.expression is None}
        columns |= {p for c in self.columns for p in c.depends_on}
        columns.add(self.tenant_column)
        return columns | {p for p, _ in self.excluded_columns}


@dataclass(frozen=True, slots=True)
class SemanticModel:
    """Every dataset the agent may query, validated as a whole at construction."""

    datasets: tuple[Dataset, ...]

    def __post_init__(self) -> None:
        names = [d.name for d in self.datasets]
        if len(set(names)) != len(names):
            raise ValueError("duplicate dataset names")
        by_name = {d.name: d for d in self.datasets}
        for dataset in self.datasets:
            _check_dataset(dataset, by_name)

    def dataset(self, name: str) -> Dataset | None:
        """The dataset with this name, or None."""
        return next((d for d in self.datasets if d.name == name), None)


def _check_dataset(dataset: Dataset, by_name: dict[str, Dataset]) -> None:
    """Refuse a dataset whose own references do not resolve: a typo here is a wrong answer later."""
    logical = [c.logical for c in dataset.columns]
    if len(set(logical)) != len(logical):
        raise ValueError(f"{dataset.name}: duplicate column names")
    singles = (dataset.year_column, dataset.method_column)
    for ref in (*singles, *dataset.month_columns, *dataset.period_columns):
        if ref is not None and dataset.column(ref) is None:
            raise ValueError(f"{dataset.name}: unknown column {ref!r}")
    for join in dataset.joins:
        _check_join(dataset, join, by_name)


def _check_join(dataset: Dataset, join: JoinDecl, by_name: dict[str, Dataset]) -> None:
    """A join must target a dataset in the same source, and name columns both sides have."""
    target = by_name.get(join.target)
    if target is None or target.source is not dataset.source or "." in join.name:
        raise ValueError(f"{dataset.name}: bad join {join.name!r}")
    for base, other in join.on:
        if dataset.column(base) is None or target.column(other) is None:
            raise ValueError(f"{dataset.name}: join {join.name!r} names an unknown column")


def default_model() -> SemanticModel:
    """The shipped model. Imported lazily: the data modules import this module's types."""
    from application.data.model_gold_credit import CREDIT_DATASETS
    from application.data.model_gold_facts import FACT_DATASETS
    from application.data.model_gold_units import UNIT_DATASETS
    from application.data.model_source import SOURCE_DATASETS

    return SemanticModel((*FACT_DATASETS, *UNIT_DATASETS, *CREDIT_DATASETS, *SOURCE_DATASETS))
