"""The data-query adapters sit under the tenant rule, and every built statement passes the guard. [CH-16c]

`tests/test_architecture.py` names the three adapters in its tenant rule (a narrow extension:
`lakehouse_data_query.py` and `sqlite_data_query.py` do not match `warehouse_*.py`). This file
proves the extension bites, that the adapters have no way around the helper, and that nothing
the builder can emit is refused by the read-only guard (a guard that refused real statements
would be switched off by someone, which is worse than not having it).
"""
from __future__ import annotations

import ast
from pathlib import Path

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


def test_the_statements_that_count_people_pass_the_guard_and_run_on_sqlite():
    database = build_database(MODEL)
    executor = SqliteDataQueryExecutor(lambda: database)
    counted = 0
    for dataset, seed in GENERATED:
        for dialect in (Dialect.TSQL, Dialect.SQLITE):
            spec = QuerySpec.from_dict({**random_spec(dataset, seed), "client_id": CLIENT_A})
            built = build_query(spec, MODEL, dialect, count_people=True)
            assert_read_only(built.sql)
            if dialect is Dialect.SQLITE and built.counts_people:
                counted += 1
                rows = executor.execute(built.sql, built.params, client_id=CLIENT_A, timeout_s=5, max_rows=built.plan.limit)
                assert not rows.rows or len(rows.rows[0]) == len(built.plan.result_columns) + 1, "one hidden size column"
    assert counted, "the generator reaches an aggregate over an employee-level dataset"


def _capability_run_calls() -> list[tuple[str, ast.Call]]:
    """Every `<something>.run(..., principal=...)` call in the capabilities: the shape of a data-service call."""
    calls = []
    for path in sorted((Path(__file__).resolve().parents[1] / "application" / "capabilities").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run" \
                    and any(k.arg == "principal" for k in node.keywords):
                calls.append((path.name, node))
    return calls


def test_every_capability_that_runs_a_data_query_states_whether_small_groups_are_suppressed():
    """A new tool that calls the service and forgets the keyword would get the safe default, but the
    decision about WHO is exempt belongs in the capability, in the open, so it is required to be written."""
    calls = _capability_run_calls()
    assert {name for name, _ in calls} >= {"data_query.py"}, "the scan found the data tools"
    for name, call in calls:
        assert any(k.arg == "suppress_small_groups" for k in call.keywords), f"{name} runs a query without saying who is exempt"


def test_the_scan_notices_a_run_without_the_keyword():
    call = ast.parse("service().run(spec, principal=who)").body[0].value
    assert not any(k.arg == "suppress_small_groups" for k in call.keywords)


def test_only_the_service_executes_a_built_query_and_only_it_applies_the_group_rule():
    root = Path(__file__).resolve().parents[1] / "application"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "withhold(" in text and path.name not in ("service.py", "small_groups.py"):
            raise AssertionError(f"{path.name} applies the small-group rule; only the data service may")
        if "count_people=" in text and path.name not in ("service.py", "build.py"):
            raise AssertionError(f"{path.name} builds a query that counts people; only the data service may decide when")


# --- RM-04: what the query layer accepts as an identifier or a SQL fragment is closed -------------------------


def _data_layer_sources() -> list[Path]:
    return sorted((Path(__file__).resolve().parents[1] / "application" / "data").glob("*.py"))


def test_no_pattern_in_the_query_layer_anchors_with_a_dollar_sign():
    """`$` also matches before a trailing newline, so `^[a-z]+$` accepted "n\\n" as an alias and the builder
    interpolated it. A pattern here ends in `\\Z`, so what a regex calls an identifier is one."""
    offenders = []
    for path in _data_layer_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "compile" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                pattern = node.args[0].value
                if pattern.startswith("^") and pattern.endswith("$") and not pattern.endswith("\\$"):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"patterns anchored with $ instead of \\Z: {offenders}"


def test_the_scan_notices_a_dollar_anchored_pattern():
    node = ast.parse('re.compile(r"^[a-z]+$")').body[0].value
    assert node.args[0].value.endswith("$")


def test_a_derived_column_is_checked_against_the_grammar_where_the_column_is_built():
    source = (Path(__file__).resolve().parents[1] / "application" / "data" / "semantic_model.py").read_text(encoding="utf-8")
    assert "check_expression(self.logical, self.expression, self.depends_on)" in source


def test_sql_text_of_a_derived_column_is_authored_only_in_the_model_files():
    """The one SQL text a model carries is written in a `model_*.py` file, where the grammar test covers it."""
    elsewhere = [p.name for p in _data_layer_sources()
                 if "expression=" in p.read_text(encoding="utf-8") and not p.name.startswith("model_") and p.name != "semantic_model.py"]
    assert elsewhere == []
