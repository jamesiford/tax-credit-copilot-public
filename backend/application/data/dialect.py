"""SQL dialects and schema names for the statement builder. [CH-16b]

Two dialects are built: T-SQL (the Fabric Warehouse and the lakehouse SQL analytics
endpoint) and SQLite (offline tests and local development). They differ in quoting, row
limiting, and what a bound value may be, and nowhere else: the builder is one code path.

Schema names are configuration (`TCC_GOLD_SCHEMA` and friends), so the model holds only a
logical key and the deployed name arrives here, validated as a plain identifier, because
it is interpolated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from application.data.semantic_model import IDENTIFIER, ColType, Column, SchemaKey


class Dialect(str, Enum):
    """The SQL flavours the builder emits."""

    TSQL = "tsql"
    SQLITE = "sqlite"


@dataclass(frozen=True, slots=True)
class SchemaNames:
    """Deployed schema names for the model's logical schema keys."""

    gold: str = "tcc_gold"
    ops: str = "tcc_ops"
    source: str = "tcc_source"

    def __post_init__(self) -> None:
        for name in (self.gold, self.ops, self.source):
            if not IDENTIFIER.match(name):
                raise ValueError(f"not a plain schema name: {name!r}")

    def name(self, key: SchemaKey) -> str:
        """The deployed schema name for a logical key."""
        return {SchemaKey.GOLD: self.gold, SchemaKey.OPS: self.ops, SchemaKey.SOURCE: self.source}[key]


DEFAULT_SCHEMAS = SchemaNames()


def quote(dialect: Dialect, identifier: str) -> str:
    """A validated identifier in the dialect's quotes. Never called with caller text."""
    if not IDENTIFIER.match(identifier):
        raise ValueError(f"refusing to quote a non-identifier: {identifier!r}")
    return f"[{identifier}]" if dialect is Dialect.TSQL else f'"{identifier}"'


def table_name(dialect: Dialect, schema: str, table: str) -> str:
    """`[schema].[table]`, both from the model and configuration."""
    return f"{quote(dialect, schema)}.{quote(dialect, table)}"


def column_sql(dialect: Dialect, column: Column, alias: str) -> str:
    """A column as it is written in SQL: `alias.[physical]`, or its dialect's expression for a derived column."""
    if column.expression is not None:
        return column.expression[0 if dialect is Dialect.TSQL else 1].replace("{t}", alias)
    return f"{alias}.{quote(dialect, column.physical)}"


def bind_value(dialect: Dialect, value: Any) -> Any:
    """A coerced value as the dialect's driver accepts it as a parameter.

    SQLite's driver has no decimal or date types (and deprecates its default adapters),
    so those travel as a float and an ISO string; T-SQL keeps the exact types.
    """
    if isinstance(value, bool):
        return int(value)
    if dialect is Dialect.TSQL:
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def cast_for_sum(expression: str, type_: ColType) -> str:
    """Wrap a flag so it can be summed: a T-SQL BIT cannot be."""
    return f"SUM(CAST({expression} AS INT))" if type_ is ColType.BOOL else f"SUM({expression})"


def cast_for_avg(dialect: Dialect, expression: str, type_: ColType) -> str:
    """AVG of an integer column in T-SQL is an integer; widen it so a mean is a mean."""
    if dialect is Dialect.TSQL and type_ is ColType.INT:
        return f"AVG(CAST({expression} AS DECIMAL(19,4)))"
    return f"AVG({expression})"
