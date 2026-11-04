"""The data-query adapters sit under the tenant rule, and every built statement passes the guard. [CH-16c]

`tests/test_architecture.py` names the three adapters in its tenant rule (a narrow extension:
`lakehouse_data_query.py` and `sqlite_data_query.py` do not match `warehouse_*.py`). This file
proves the extension bites, that the adapters have no way around the helper, and that nothing
the builder can emit is refused by the read-only guard (a guard that refused real statements
would be switched off by someone, which is worse than not having it).
"""
from __future__ import annotations

import ast

import pytest

from application.data.dialect import Dialect
from application.data.build import build_query
from application.data.executor import assert_read_only
from application.data.spec import QuerySpec
from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
from tests.data_fixture import CLIENT_A, build_database
from tests.test_architecture import _DATA_QUERY_ADAPTERS, _PERSISTENCE, _tenant_scoped_modules, direct_executions
from tests.test_data_build_sql import GENERATED, MODEL, random_spec


def test_every_data_query_adapter_is_under_the_tenant_rule():
    names = {p.name for p in _tenant_scoped_modules()}
    assert set(_DATA_QUERY_ADAPTERS) <= names
    for name in _DATA_QUERY_ADAPTERS:
        assert (_PERSISTENCE / name).exists()


@pytest.mark.parametrize("name", _DATA_QUERY_ADAPTERS)
def test_the_adapters_execute_only_through_the_tenant_helper(name):
    source = (_PERSISTENCE / name).read_text(encoding="utf-8")
    assert direct_executions(source) == []


@pytest.mark.parametrize("name, original, mutated", [
    ("warehouse_data_query.py", "TenantScopedQuery(client_id).execute(cursor, sql, list(params))", "cursor.execute(sql, list(params))"),
    ("sqlite_data_query.py", "TenantScopedQuery(client_id).execute(cursor, sql, list(params))", "cursor.execute(sql, list(params))"),
])
def test_undoing_the_helper_in_a_data_query_adapter_is_caught(name, original, mutated):
    source = (_PERSISTENCE / name).read_text(encoding="utf-8")
    assert original in source, f"{name} changed; update this mutation"
    assert direct_executions(source.replace(original, mutated, 1)), f"mutating {name} went undetected"


@pytest.mark.parametrize("name", _DATA_QUERY_ADAPTERS)
def test_no_data_query_adapter_can_leave_the_tenant(name):
    tree = ast.parse((_PERSISTENCE / name).read_text(encoding="utf-8"))
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "tenant_exempt" not in used and "TenantExemptQuery" not in used


@pytest.mark.parametrize("name", _DATA_QUERY_ADAPTERS)
def test_every_adapter_refuses_non_select_before_binding(name):
    source = (_PERSISTENCE / name).read_text(encoding="utf-8")
    if name == "lakehouse_data_query.py":
        assert "TsqlDataQueryExecutor" in source
        return
    assert source.index("assert_read_only(sql)") < source.index("TenantScopedQuery(")


@pytest.mark.parametrize("dataset, seed", GENERATED, ids=lambda v: getattr(v, "name", v))
@pytest.mark.parametrize("dialect", [Dialect.TSQL, Dialect.SQLITE])
def test_the_guard_accepts_every_statement_the_builder_can_emit(dataset, seed, dialect):
    built = build_query(QuerySpec.from_dict({**random_spec(dataset, seed), "client_id": CLIENT_A}), MODEL, dialect)
    assert_read_only(built.sql)


def test_every_dataset_runs_end_to_end_through_the_adapter_on_sqlite():
    database = build_database(MODEL)
    executor = SqliteDataQueryExecutor(lambda: database)
    for dataset, seed in GENERATED:
        if seed % 5:
            continue
        built = build_query(QuerySpec.from_dict({**random_spec(dataset, seed), "client_id": CLIENT_A}), MODEL, Dialect.SQLITE)
        rows = executor.execute(built.sql, built.params, client_id=CLIENT_A, timeout_s=5, max_rows=built.plan.limit)
        assert rows.row_count <= built.plan.limit
