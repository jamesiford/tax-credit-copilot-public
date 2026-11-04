"""Composition and settings of the data-query layer. [CH-16c]

Covers what no adapter test can: how settings choose executors, that the lakehouse source is OFF
by default, that limits are clamped, that the lakehouse endpoint has its own settings and its own
pool, and that the shared rate limiter still serves the gateway from its new home.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

import bootstrap.data_wiring as wiring
from application.data.exec_errors import DataSourceDisabled, DataSourceUnavailable
from application.data.semantic_model import Source
from application.data.spec import QuerySpec
from infrastructure.persistence import fabric_warehouse
from infrastructure.persistence.lakehouse_data_query import LakehouseDataQueryExecutor
from infrastructure.persistence.lakehouse_sql_connection import LakehouseSqlConnection
from infrastructure.persistence.warehouse_data_query import TsqlDataQueryExecutor, WarehouseDataQueryExecutor

WAREHOUSE = {"WAREHOUSE_SERVER": "host.example", "WAREHOUSE_DATABASE": "wh"}
PAYROLL = QuerySpec.from_dict({"dataset": "payroll", "client_id": 1001, "measures": [{"column": "*", "agg": "count"}]})


@pytest.fixture(autouse=True)
def _clean_service():
    wiring.set_data_query_service(None)
    yield
    wiring.set_data_query_service(None)


def test_the_lakehouse_source_is_off_unless_the_flag_is_truthy():
    assert wiring.source_enabled({}) is False
    assert wiring.source_enabled({"DATA_QUERY_SOURCE_ENABLED": "false"}) is False
    assert wiring.source_enabled({"DATA_QUERY_SOURCE_ENABLED": "0"}) is False
    for value in ("1", "true", "TRUE", " yes ", "on"):
        assert wiring.source_enabled({"DATA_QUERY_SOURCE_ENABLED": value}) is True


def test_defaults_are_twenty_seconds_five_hundred_rows_and_four_slots():
    limits = wiring.limits_from_env({})
    assert (limits.timeout_s, limits.hard_max_rows, limits.max_concurrency) == (20, 500, 4)


def test_settings_are_clamped_and_a_bad_value_falls_back():
    limits = wiring.limits_from_env({"DATA_QUERY_TIMEOUT_SECONDS": "9999", "DATA_QUERY_MAX_ROWS": "100000",
                                     "DATA_QUERY_MAX_CONCURRENCY": "0"})
    assert (limits.timeout_s, limits.hard_max_rows, limits.max_concurrency) == (120, 500, 1)
    assert wiring.limits_from_env({"DATA_QUERY_TIMEOUT_SECONDS": "soon"}).timeout_s == 20
    assert wiring.limits_from_env({"DATA_QUERY_MAX_ROWS": "50"}).hard_max_rows == 50


def test_the_warehouse_executor_is_chosen_where_the_warehouse_is_configured():
    executors = wiring.build_executors(WAREHOUSE, wiring.schemas_from_config())
    assert isinstance(executors[Source.WAREHOUSE], WarehouseDataQueryExecutor)
    assert Source.LAKEHOUSE not in executors


def test_the_lakehouse_executor_needs_its_flag():
    executors = wiring.build_executors({**WAREHOUSE, "DATA_QUERY_SOURCE_ENABLED": "true"}, wiring.schemas_from_config())
    assert isinstance(executors[Source.LAKEHOUSE], LakehouseDataQueryExecutor)


def test_nothing_configured_means_typed_unavailable_never_a_fallback():
    service = wiring.build_data_query_service({})
    assert service.available_sources() == frozenset()
    with pytest.raises(DataSourceDisabled):
        service.run(PAYROLL, principal="u")
    warehouse_only = QuerySpec.from_dict({"dataset": "run_manifest", "client_id": 1001, "select": ["run_id"]})
    with pytest.raises(DataSourceUnavailable):
        service.run(warehouse_only, principal="u")


def test_a_local_sqlite_directory_serves_both_sources_with_the_lakehouse_still_gated(tmp_path):
    for name in ("tcc_gold", "tcc_ops", "tcc_source"):
        sqlite3.connect(tmp_path / f"{name}.db").close()
    off = wiring.build_data_query_service({"DATA_QUERY_SQLITE_DIR": str(tmp_path)})
    assert off.available_sources() == {Source.WAREHOUSE}
    on = wiring.build_data_query_service({"DATA_QUERY_SQLITE_DIR": str(tmp_path), "DATA_QUERY_SOURCE_ENABLED": "1"})
    assert on.available_sources() == {Source.WAREHOUSE, Source.LAKEHOUSE}


def test_the_service_is_built_once_and_can_be_replaced():
    first = wiring.get_data_query_service()
    assert wiring.get_data_query_service() is first
    wiring.set_data_query_service(None)
    assert wiring.get_data_query_service() is not first


# ------------------------------------------------------------------ the lakehouse endpoint


def test_the_lakehouse_endpoint_has_its_own_settings_with_warehouse_style_defaults(monkeypatch):
    for name in ("LAKEHOUSE_SQL_SERVER", "LAKEHOUSE_SQL_DATABASE", "WAREHOUSE_SERVER", "FABRIC_LAKEHOUSE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WAREHOUSE_SERVER", "shared.example")
    monkeypatch.setenv("FABRIC_LAKEHOUSE", "lh_name")
    fallback = LakehouseSqlConnection()
    assert (fallback.server, fallback.database) == ("shared.example", "lh_name")
    monkeypatch.setenv("LAKEHOUSE_SQL_SERVER", "endpoint.example")
    monkeypatch.setenv("LAKEHOUSE_SQL_DATABASE", "lh_endpoint")
    explicit = LakehouseSqlConnection()
    assert (explicit.server, explicit.database) == ("endpoint.example", "lh_endpoint")
    assert "Server=endpoint.example,1433;Database=lh_endpoint;" in explicit.connection_string()


def test_an_unset_lakehouse_endpoint_names_the_setting_to_supply(monkeypatch):
    for name in ("LAKEHOUSE_SQL_SERVER", "LAKEHOUSE_SQL_DATABASE", "WAREHOUSE_SERVER", "FABRIC_LAKEHOUSE"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(fabric_warehouse.WarehouseNotConfigured) as caught:
        LakehouseSqlConnection().require_configuration()
    assert "LAKEHOUSE_SQL_SERVER" in str(caught.value) and "LAKEHOUSE_SQL_DATABASE" in str(caught.value)


class _Raw:
    def __init__(self):
        self.closed, self.rolled_back = False, 0

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


class _OpensRaw(LakehouseSqlConnection):
    def open(self):
        return _Raw()


def test_the_lakehouse_connection_never_touches_the_warehouse_pool():
    before = list(fabric_warehouse._POOL)
    connection = _OpensRaw(server="s", database="d")
    with connection.connect() as first:
        pass
    assert fabric_warehouse._POOL == before
    with connection.connect() as second:
        assert second is first
    assert first.rolled_back >= 1 and not first.closed
    assert connection.prewarm() == 0 and connection.keepalive() == 0


def test_a_failed_lakehouse_connection_is_discarded_not_pooled():
    connection = _OpensRaw(server="s", database="d")
    with pytest.raises(RuntimeError):
        with connection.connect() as live:
            raise RuntimeError("link dropped")
    assert live.closed is True
    with connection.connect() as fresh:
        assert fresh is not live


def test_the_lakehouse_pool_keeps_at_most_two_idle_connections():
    connection = _OpensRaw(server="s", database="d")
    opened = [connection.acquire() for _ in range(4)]
    for item in opened:
        connection.release(item)
    assert sum(1 for item in opened if item.closed) == 2


# ------------------------------------------------------------------ one implementation of the limiter


def test_the_gateway_limiter_is_the_application_one():
    from application.rate_limit import RateLimiter
    from channel.limiter import RateLimiter as GatewayLimiter

    assert GatewayLimiter is RateLimiter


def test_the_lakehouse_executor_reuses_the_tsql_core_and_adds_no_execution_path():
    assert issubclass(LakehouseDataQueryExecutor, TsqlDataQueryExecutor)
    source = (Path(__file__).resolve().parents[1] / "infrastructure" / "persistence" / "lakehouse_data_query.py").read_text("utf-8")
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Attribute) and n.attr in ("execute", "cursor")]
    assert calls == []
