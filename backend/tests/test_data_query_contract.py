"""One contract, every adapter: the Warehouse, the Lakehouse endpoint and SQLite. [CH-16c]

The adapters differ in engine and nothing else, so the same assertions run against each:
only a single SELECT runs, the client is bound by the tenant helper, the row cap reports its
truncation, a timeout is typed and returns nothing, and a database failure says nothing about
the statement. The T-SQL adapters run against a scripted fake connection (no engine offline).
"""
from __future__ import annotations

import pytest

from application.data.exec_errors import DataSourceUnavailable, NotReadOnly, QueryFailed, QueryTimeout
from infrastructure.persistence.tenant_sql import TenantScopeViolation
from tests.data_query_fakes import CLIENT, OTHER, FakeTsqlConnection, TsqlHarness, harnesses

ADAPTERS = harnesses()


@pytest.fixture(params=[h.name for h in ADAPTERS])
def harness(request):
    return next(h for h in harnesses() if h.name == request.param)


def run(harness, sql=None, *, max_rows=500, timeout_s=5.0, client=CLIENT):
    return harness.executor().execute(
        harness.statement if sql is None else sql, [], client_id=client, timeout_s=timeout_s, max_rows=max_rows)


@pytest.mark.parametrize("sql", [
    "INSERT INTO data_t VALUES (1, 1)",
    "DELETE FROM data_t WHERE {tenant}",
    "UPDATE data_t SET v = 1 WHERE {tenant}",
    "DROP TABLE data_t",
    "EXEC sp_who",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT v FROM data_t WHERE {tenant}; DROP TABLE data_t",
    "SELECT v FROM data_t WHERE {tenant} -- trailing",
    "SELECT v /* hidden */ FROM data_t WHERE {tenant}",
    "",
])
def test_only_a_single_select_is_ever_run(harness, sql):
    harness.seed(3)
    with pytest.raises(NotReadOnly):
        run(harness, sql)
    assert harness.bound() is None


def test_a_select_runs_in_any_case_and_with_leading_space(harness):
    harness.seed(2)
    assert run(harness, "  select v FROM data_t WHERE {tenant} ORDER BY v").row_count == 2


def test_the_client_is_bound_first_by_the_tenant_helper(harness):
    harness.seed(3)
    rows = run(harness)
    assert all(r[0] != 999 for r in rows.rows)
    bound = harness.bound()
    if bound is not None:
        sql, params = bound
        assert sql == "SELECT v FROM data_t WHERE client_id = ? ORDER BY v"
        assert params == [CLIENT]


def test_another_clients_rows_are_never_returned(harness):
    harness.seed(3)
    assert 999 not in {r[0] for r in run(harness, client=CLIENT).rows}
    if harness.name == "sqlite":
        assert [r[0] for r in run(harness, client=OTHER).rows] == [999]


def test_a_statement_without_the_tenant_marker_is_refused(harness):
    harness.seed(1)
    with pytest.raises(TenantScopeViolation):
        run(harness, "SELECT v FROM data_t")


def test_rows_beyond_the_cap_are_dropped_and_reported(harness):
    harness.seed(8)
    rows = run(harness, max_rows=5)
    assert rows.row_count == 5 and rows.truncated is True
    assert rows.columns and len(rows.rows[0]) == len(rows.columns)


def test_exactly_the_cap_is_not_truncated(harness):
    harness.seed(5)
    rows = run(harness, max_rows=5)
    assert rows.row_count == 5 and rows.truncated is False


def test_fewer_rows_than_the_cap_is_complete(harness):
    harness.seed(2)
    rows = run(harness, max_rows=5)
    assert rows.row_count == 2 and rows.truncated is False


def test_a_timeout_is_typed_and_returns_no_rows(harness):
    sql = harness.slow()
    with pytest.raises(QueryTimeout) as caught:
        run(harness, sql, timeout_s=0.05)
    assert caught.value.code == "query_timeout"


def test_a_database_failure_is_generic_and_does_not_echo_the_statement(harness):
    harness.seed(1)
    harness.broken()
    with pytest.raises(QueryFailed) as caught:
        run(harness)
    assert "secret_table" not in str(caught.value) and "data_t" not in str(caught.value)


@pytest.mark.parametrize("kind", ["warehouse", "lakehouse"])
def test_a_tsql_adapter_sets_the_driver_timeout_and_puts_it_back(kind):
    harness = TsqlHarness(kind)
    harness.seed(1)
    run(harness, timeout_s=12.7)
    live = harness.connection.live
    assert live.timeouts_seen == [12] and live.timeout == 0
    assert live.cursors_closed == 1


@pytest.mark.parametrize("kind", ["warehouse", "lakehouse"])
def test_a_failed_tsql_query_discards_the_connection_and_restores_the_timeout(kind):
    harness = TsqlHarness(kind)
    harness.slow()
    with pytest.raises(QueryTimeout):
        run(harness, timeout_s=3)
    assert harness.connection.failed is True and harness.connection.live.timeout == 0


@pytest.mark.parametrize("kind", ["warehouse", "lakehouse"])
def test_an_unconfigured_tsql_adapter_is_a_typed_unavailable(kind):
    adapter = TsqlHarness(kind)
    adapter.connection = FakeTsqlConnection(configured=False)
    with pytest.raises(DataSourceUnavailable) as caught:
        run(adapter)
    assert kind in str(caught.value)
