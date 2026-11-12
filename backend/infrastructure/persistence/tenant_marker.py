"""The `{tenant}` marker and the closed set of client columns it may name. [DATA-4, CH-16b, 06]

Split from `tenant_sql.py`, which applies it. `{tenant:alias@Column}` names a client column other than `client_id`:
the lakehouse's tenant column, spelled as the source mapping spells it (`Accountid` in one estate, `AccountId` in
another). The set is closed and computed from the mapping on each use, so a mapping change is honoured and a column
the mapping does not name is refused.
"""
from __future__ import annotations

import re

MARKER = re.compile(r"\{tenant(?::([A-Za-z_][A-Za-z0-9_]*))?(?:@([A-Za-z_][A-Za-z0-9_]*))?\}")
#: The marker must be the first term of a WHERE or ON clause.
ANCHORED = re.compile(r"\b(WHERE|ON)\s+$", re.IGNORECASE)


class TenantScopeViolation(ValueError):
    """A statement that could return or write another client's rows."""


def closed_set() -> frozenset[str]:
    """`client_id` and every tenant column the source mapping names."""
    from data.source.mapping import tenant_columns

    return frozenset({"client_id"}) | tenant_columns()


def count_params(sql: str) -> int:
    """Count `?` placeholders outside string literals."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql).count("?")


def predicate(marker: re.Match[str]) -> str:
    """The `[alias.]column = ?` a marker stands for; the column must be in the closed set."""
    alias, column = marker.group(1), marker.group(2) or "client_id"
    if column not in closed_set():
        raise TenantScopeViolation(f"{column!r} is not a known tenant column")
    return f"{alias + '.' if alias else ''}{column} = ?"
