"""Statement building: shape, isolation, bound values and hostile input. [CH-16b]"""
from __future__ import annotations

import random
import re

import pytest

from application.data.build import TRUNCATION_PROBE, BuiltQuery, build_query, build_sql
from application.data.dialect import Dialect, SchemaNames
from application.data.errors import QueryError
from application.data.semantic_model import ColType, Column, Op, Sensitivity, default_model
from application.data.spec import METHODS, QuerySpec
from infrastructure.persistence.tenant_sql import TenantScopedQuery
from tests.data_fixture import CLIENT_A, CLIENT_B, ROWS_PER_CLIENT, build_database, run

MODEL = default_model()
DIALECTS = (Dialect.TSQL, Dialect.SQLITE)
UNSCOPED_CLAUSE = re.compile(r"\b(?:WHERE|ON)\s+(?!\{tenant)")


@pytest.fixture(scope="module")
def db():
    return build_database(MODEL)


def spec(dataset="unit_year_master", **kw) -> QuerySpec:
    return QuerySpec.from_dict({"dataset": dataset, "client_id": CLIENT_A, **kw})


def test_tsql_golden_statement_and_params():
    sql, params = build_sql(spec(select=["worksite_id"], tax_years=[2023], method="min_max", order_by=[{"column": "credit", "direction": "desc"}],
                                 measures=[{"column": "annual_credit_usd", "agg": "sum", "as": "credit"}]), MODEL, Dialect.TSQL)
    assert sql == (
        "SELECT TOP (101) t.[method] AS [method], t.[worksite_id] AS [worksite_id], SUM(t.[annual_credit_usd]) AS [credit] "
        "FROM [tcc_gold].[unit_year_master] AS t WHERE {tenant:t} AND t.[is_current] = ? AND t.[tax_year] = ? AND t.[method] = ? "
        "GROUP BY t.[method], t.[worksite_id] ORDER BY [credit] DESC, t.[method] ASC, t.[worksite_id] ASC"
    )
    assert params == [1, 2023, "min_max"]


def test_sqlite_golden_statement_uses_limit_and_double_quotes():
    sql, params = build_sql(spec(select=["worksite_id"], measures=[{"column": "*", "agg": "count"}], limit=7), MODEL, Dialect.SQLITE)
    assert sql == (
        'SELECT t."method" AS "method", t."worksite_id" AS "worksite_id", COUNT(*) AS "row_count" '
        'FROM "tcc_gold"."unit_year_master" AS t WHERE {tenant:t} AND t."is_current" = ? '
        'GROUP BY t."method", t."worksite_id" ORDER BY t."method" ASC, t."worksite_id" ASC LIMIT 8'
    )
    assert params == [1]


def test_a_live_run_dataset_pins_the_clients_live_run_with_a_scoped_subquery():
    sql, params = build_sql(spec("employee_eligibility", select=["tax_year"], measures=[{"column": "eligible", "agg": "sum"}],
                                 tax_years=[2023, 2024], method="pay_period"), MODEL, Dialect.TSQL)
    assert "t.[run_id] = (SELECT TOP 1 m.[run_id] FROM [tcc_ops].[run_manifest] AS m WHERE {tenant:m} AND m.[run_status] = ?" in sql
    assert "SUM(CAST(t.[eligible] AS INT))" in sql and "t.[tax_year] IN (?, ?)" in sql
    assert params == ["success", 2023, 2024, "pay_period"]


def test_a_lakehouse_join_scopes_both_tables_by_account_id_and_keeps_every_base_row():
    sql, params = build_sql(spec("payroll", select=["location.location_name", "pay_year"], measures=[{"column": "wages", "agg": "avg"}],
                                 filters=[{"column": "pay_code_info.pay_code", "op": "contains", "value": "Reg"}]), MODEL, Dialect.TSQL)
    assert "FROM [tcc_source].[Payroll] AS t LEFT JOIN [tcc_source].[Location] AS location ON {tenant:location@AccountId} AND t.[LocationId] = location.[LocationId]" in sql
    assert "LEFT JOIN [tcc_source].[PayCode] AS pay_code_info ON {tenant:pay_code_info@AccountId}" in sql
    assert "WHERE {tenant:t@AccountId} AND LOWER(pay_code_info.[PayCode]) LIKE ? ESCAPE '\\'" in sql
    assert "YEAR(COALESCE(t.[PayDate], t.[PayPeriodEnd]))" in sql and params == ["%reg%"]


def test_an_integer_mean_is_widened_in_tsql_so_it_is_a_mean():
    sql, _ = build_sql(spec("employee_eligibility", select=["tax_year"], measures=[{"column": "days", "agg": "avg"}]), MODEL, Dialect.TSQL)
    assert "AVG(CAST(t.[days] AS DECIMAL(19,4)))" in sql
    sql, _ = build_sql(spec("employee_eligibility", select=["tax_year"], measures=[{"column": "days", "agg": "avg"}]), MODEL, Dialect.SQLITE)
    assert 'AVG(t."days")' in sql


def test_the_limit_fetches_one_extra_row_so_truncation_can_be_reported():
    assert TRUNCATION_PROBE == 1
    assert "TOP (501)" in build_sql(spec(select=["worksite_id"], limit=500), MODEL, Dialect.TSQL)[0]
    assert build_sql(spec(select=["worksite_id"], limit=500), MODEL, Dialect.SQLITE)[0].endswith("LIMIT 501")


def test_schema_names_are_configuration_and_validated():
    sql, _ = build_sql(spec(select=["worksite_id"]), MODEL, Dialect.TSQL, SchemaNames(gold="gold_v2"))
    assert "[gold_v2].[unit_year_master]" in sql
    for bad in ("x; DROP", "a b", "", "a]b"):
        with pytest.raises(ValueError):
            SchemaNames(gold=bad)


def test_build_query_carries_the_plan_for_provenance_and_the_statement_is_select_only():
    built = build_query(spec(select=["worksite_id"]), MODEL, Dialect.TSQL)
    assert isinstance(built, BuiltQuery) and built.plan.client_id == CLIENT_A and built.sql.startswith("SELECT ")
    assert ";" not in built.sql


def test_an_invalid_specification_builds_nothing():
    with pytest.raises(QueryError):
        build_sql(spec(select=["employee_id"], dataset="employee_eligibility"), MODEL, Dialect.TSQL)


# --- the client scope is the first predicate, for every dataset ---------------------------------


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("dataset", MODEL.datasets, ids=lambda d: d.name)
def test_the_client_scope_is_the_first_predicate_of_every_where_and_on(dataset, dialect):
    column = next(c for c in dataset.columns if c.queryable and c.role.value != "measure")
    select = [column.logical] if dataset.method_column is None else []
    sql, params = build_sql(spec(dataset.name, select=select, measures=[{"column": "*", "agg": "count"}]), MODEL, dialect)
    assert sql.count(" WHERE ") >= 1 and not UNSCOPED_CLAUSE.findall(sql), sql
    assert re.search(r"FROM \S+ AS t(?: LEFT JOIN .*?)? WHERE \{tenant:t(@AccountId)?\}", sql)
    bound, values = TenantScopedQuery(CLIENT_A).bind(sql, params)
    first = bound.index("WHERE ") + len("WHERE ")
    assert bound[first:].startswith(("t.client_id = ?", "t.AccountId = ?"))
    assert CLIENT_A in values and sql.count("?") == len(params)


@pytest.mark.parametrize("dataset", [d for d in MODEL.datasets if d.joins], ids=lambda d: d.name)
def test_every_declared_join_is_scoped_in_its_on_clause(dataset):
    refs = [f"{j.name}.{MODEL.dataset(j.target).columns[0].logical}" for j in dataset.joins]
    sql, params = build_sql(spec(dataset.name, select=refs, measures=[{"column": "*", "agg": "count"}]), MODEL, Dialect.TSQL)
    assert sql.count(" LEFT JOIN ") == len(dataset.joins) and not UNSCOPED_CLAUSE.findall(sql)
    _, values = TenantScopedQuery(CLIENT_A).bind(sql, params)
    assert values.count(CLIENT_A) == len(dataset.joins) + 1


def test_the_tenant_helper_refuses_the_statement_if_the_scope_were_not_first():
    sql, params = build_sql(spec(select=["worksite_id"]), MODEL, Dialect.TSQL)
    from infrastructure.persistence.tenant_sql import TenantScopeViolation

    with pytest.raises(TenantScopeViolation):
        TenantScopedQuery(CLIENT_A).bind(sql.replace("WHERE {tenant:t} AND", "WHERE 1 = 1 AND {tenant:t} AND"), params)
    with pytest.raises(TenantScopeViolation):
        TenantScopedQuery(CLIENT_A).bind(sql.replace("{tenant:t}", "1 = 1"), params)


@pytest.mark.parametrize("dataset", MODEL.datasets, ids=lambda d: d.name)
def test_a_query_returns_only_the_callers_clients_live_rows(dataset, db):
    select = ["location.location_name"] if dataset.name == "payroll" else []
    sql, params = build_sql(spec(dataset.name, select=select, measures=[{"column": "*", "agg": "count"}]), MODEL, Dialect.SQLITE)
    for client in (CLIENT_A, CLIENT_B):
        rows = run(db, sql, params, client)
        assert sum(r[-1] for r in rows) == ROWS_PER_CLIENT, (dataset.name, client, rows)


def test_a_join_never_borrows_another_clients_rows(db):
    sql, params = build_sql(spec("payroll", select=["location.location_name"], measures=[{"column": "*", "agg": "count"}]), MODEL, Dialect.SQLITE)
    names = {r[0] for r in run(db, sql, params, CLIENT_A)}
    assert names and all(str(CLIENT_A) in n for n in names) and not any(str(CLIENT_B) in n for n in names)


def test_superseded_rows_are_never_returned(db):
    for name in ("unit_year_master", "unit_credit_installment"):
        sql, params = build_sql(spec(name, select=["worksite_id"], measures=[{"column": "*", "agg": "count"}]), MODEL, Dialect.SQLITE)
        assert sum(r[-1] for r in run(db, sql, params, CLIENT_A)) == ROWS_PER_CLIENT
    sql, params = build_sql(spec("employee_eligibility", select=["record_token"]), MODEL, Dialect.SQLITE)
    assert not any("old-" in str(v) for r in run(db, sql, params, CLIENT_A) for v in r)


# --- hostile values never reach the statement text -----------------------------------------------

HOSTILE = [
    "'; DROP TABLE tcc_gold.unit_year_master; --", "x' OR '1'='1", "1; SELECT * FROM sys.tables", "x/* c */y", "a--b", "ＤＲＯＰ ＴＡＢＬＥ x",
    "a\x00b", "a\u202eb", "EXEC xp_cmdshell 'dir'", "Robert'); DROP TABLE Students;--", "50%", "a_b", "[a-z]", "back\\slash", "ʼ OR ʼ1ʼ=ʼ1",
    "x" * 100, "tab\tand\nnewline", "\ud800",
]


@pytest.mark.parametrize("value", HOSTILE)
@pytest.mark.parametrize("op", ["eq", "in", "contains"])
def test_a_hostile_value_is_refused_or_bound_and_never_part_of_the_statement(value, op):
    payload = [value] if op == "in" else value
    dataset, column = ("employee_period_fact", "job_title") if op == "contains" else ("unit_year_master", "worksite_id")
    try:
        sql, params = build_sql(spec(dataset, select=["tax_year"], filters=[{"column": column, "op": op, "value": payload}]), MODEL, Dialect.TSQL)
    except QueryError:
        return
    stripped = re.sub(r"\s+", " ", sql)
    assert value not in sql and value.strip() not in stripped and ";" not in sql and "--" not in sql
    assert sql.count("?") == len(params)
    expected = value.lower() if op == "contains" else value
    assert any(expected.replace("\\", "") in str(p).replace("\\", "") for p in params)


@pytest.mark.parametrize("bad", ["x; DROP", "a b", "a-b", "A", "1x", "x" * 41, "a'b", "a\"b", "é"])
def test_a_measure_alias_is_only_ever_a_plain_lowercase_identifier(bad):
    with pytest.raises(QueryError):
        build_sql(spec(select=["worksite_id"], measures=[{"column": "*", "agg": "count", "as": bad}]), MODEL, Dialect.TSQL)


def test_like_wildcards_in_a_contains_value_are_escaped_to_literals(db):
    sql, params = build_sql(spec("employee_period_fact", select=["job_title"], filters=[{"column": "job_title", "op": "contains", "value": "50%_[x]\\"}]),
                            MODEL, Dialect.TSQL)
    assert params[-1] == "%50\\%\\_\\[x]\\\\%"
    for pattern, expected in (("j_b", 0), ("o%t", 0), ("job", True)):
        sql, params = build_sql(spec("employee_period_fact", select=["job_title"], filters=[{"column": "job_title", "op": "contains", "value": pattern}]),
                                MODEL, Dialect.SQLITE)
        rows = run(db, sql, params, CLIENT_A)
        assert bool(rows) is bool(expected), (pattern, rows)


def test_contains_is_case_insensitive_the_same_way_in_both_dialects(db):
    for value in ("JOB_TITLE", "job_title", "Job_Title"):
        sql, params = build_sql(spec("employee_period_fact", select=["job_title"], filters=[{"column": "job_title", "op": "contains", "value": value}]),
                                MODEL, Dialect.SQLITE)
        assert run(db, sql, params, CLIENT_A)
        assert params[-1] == f"%{value.lower().replace('_', chr(92) + '_')}%"


# --- property style: generated valid specifications ---------------------------------------------


def _queryable(dataset):
    return [c for c in dataset.columns if c.queryable]


def _refs(dataset) -> list[tuple[str, Column]]:
    refs = [(c.logical, c) for c in _queryable(dataset)]
    for join in dataset.joins:
        refs += [(f"{join.name}.{c.logical}", c) for c in _queryable(MODEL.dataset(join.target))]
    return refs


def _value(column: Column, rnd: random.Random, tag: str):
    if column.choices:
        return rnd.choice(column.choices)
    return {ColType.INT: lambda: rnd.randint(1, 9), ColType.DECIMAL: lambda: round(rnd.uniform(0, 9), 2),
            ColType.BOOL: lambda: rnd.choice([True, False]), ColType.DATE: lambda: "2023-01-05",
            ColType.DATETIME: lambda: "2023-01-05 10:00:00", ColType.TEXT: lambda: f"zq{tag}{rnd.randint(100, 999)}"}[column.type]()


def _filter(ref: str, column: Column, rnd: random.Random, tag: str) -> dict:
    op = rnd.choice(sorted(column.operators, key=lambda o: o.value))
    one = _value(column, rnd, tag)
    value = {Op.IN: [one, _value(column, rnd, tag + "b")], Op.BETWEEN: sorted([one, _value(column, rnd, tag)])}.get(op, one)
    if op is Op.BETWEEN and column.type is ColType.DATE:
        value = ["2023-01-01", "2023-12-31"]
    return {"column": ref, "op": op.value, "value": value}


def random_spec(dataset, seed: int) -> dict:
    rnd = random.Random(f"{dataset.name}:{seed}")
    refs = [(r, c) for r, c in _refs(dataset) if c.logical != dataset.method_column]
    payload: dict = {"dataset": dataset.name, "client_id": CLIENT_A, "limit": rnd.choice([1, 10, 100, 500])}
    if rnd.random() < 0.6:
        dims = [(r, c) for r, c in refs if c.role.value != "measure"]
        payload["select"] = [r for r, _ in rnd.sample(dims, min(len(dims), rnd.randint(0, 3)))]
        measures = [{"column": "*", "agg": "count", "as": "n"}]
        for i, (r, c) in enumerate(rnd.sample(refs, min(len(refs), rnd.randint(0, 2)))):
            if c.aggregations:
                measures.append({"column": r, "agg": rnd.choice(sorted(c.aggregations, key=lambda a: a.value)).value, "as": f"m{i}"})
        payload["measures"] = measures
    else:
        payload["select"] = [r for r, _ in rnd.sample(refs, min(len(refs), rnd.randint(1, 4)))]
    filterable = [(r, c) for r, c in refs if c.operators]
    payload["filters"] = [_filter(r, c, rnd, f"{seed}x{i}") for i, (r, c) in enumerate(rnd.sample(filterable, min(len(filterable), rnd.randint(0, 3))))]
    if dataset.year_column and rnd.random() < 0.5:
        payload["tax_years"] = sorted(rnd.sample(range(2020, 2026), rnd.randint(1, 3)))
    if dataset.method_column:
        payload["method"] = rnd.choice(METHODS)
    orderable = payload["select"] + [m["as"] for m in payload.get("measures", [])]
    payload["order_by"] = [{"column": c, "direction": rnd.choice(["asc", "desc"])} for c in rnd.sample(orderable, min(len(orderable), rnd.randint(0, 2)))]
    return payload


GENERATED = [(d, seed) for d in MODEL.datasets for seed in range(25)]


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("dataset, seed", GENERATED, ids=lambda v: v.name if hasattr(v, "name") else str(v))
def test_generated_valid_specifications_build_bound_scoped_deterministic_sql(dataset, seed, dialect, db):
    payload = random_spec(dataset, seed)
    built = build_query(QuerySpec.from_dict(payload), MODEL, dialect)
    sql, params = built.as_tuple()
    assert build_sql(QuerySpec.from_dict(payload), MODEL, dialect) == (sql, params)
    assert sql.count("?") == len(params) and sql.startswith("SELECT ") and ";" not in sql
    assert not UNSCOPED_CLAUSE.findall(sql)
    bound, values = TenantScopedQuery(CLIENT_A).bind(sql, params)
    assert len(values) == len(params) + sql.count("{tenant")
    for f in payload["filters"]:
        for v in (f["value"] if isinstance(f["value"], list) else [f["value"]]):
            if isinstance(v, str) and v.startswith("zq"):
                assert v not in sql and any(v in str(p) for p in params)
    if dialect is Dialect.SQLITE:
        rows = db.execute(bound, values).fetchall()
        assert len(rows) <= payload["limit"] + TRUNCATION_PROBE
        assert all(len(r) == len(built.plan.result_columns) for r in rows)


def test_every_generated_column_choice_is_a_declared_value_and_blocked_columns_are_never_generated():
    for dataset in MODEL.datasets:
        refs = {r for r, c in _refs(dataset)}
        assert not any(c.sensitivity is Sensitivity.BLOCKED for _, c in _refs(dataset))
        assert refs
