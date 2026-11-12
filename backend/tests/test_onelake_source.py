"""Private-link endpoint, path styles and interim source table names. [03.1, 03.2]

With nothing set, every address and statement is exactly what it was before; each setting is opt-in.
The endpoint redirect is proved against a local HTTP server with the real `deltalake`, so what is
asserted is the request `deltalake` actually makes, not our description of it.
"""
from __future__ import annotations

import http.server
import socketserver
import threading
import uuid

import pytest

from config import override_settings
from data.source import onelake
from data.source.onelake import physical_table, storage_options, table_uri
from infrastructure.persistence.source_sql import SourceSqlReader

LOGICAL = ("Payroll", "Account", "Employment", "Location", "Address", "StateCountyZip", "Entity", "PayCode")


def _settings(**env):
    return override_settings({"FABRIC_LAKEHOUSE": "lh", **env})


# ------------------------------------------------------------------ names


def test_with_nothing_set_the_address_is_what_it_always_was():
    with _settings():
        assert table_uri("Payroll", workspace="ws", lakehouse="lh", schema="tcc_source") == (
            "abfss://ws@onelake.dfs.fabric.microsoft.com/lh.Lakehouse/Tables/tcc_source/Payroll"
        )
        assert [physical_table(t) for t in LOGICAL] == list(LOGICAL)


def test_a_prefix_and_lower_case_give_the_physical_name():
    with _settings(SOURCE_TABLE_PREFIX="src_dbo_", SOURCE_TABLE_CASE="lower"):
        assert physical_table("Payroll") == "src_dbo_payroll"
        assert physical_table("StateCountyZip") == "src_dbo_statecountyzip"
        assert table_uri("Payroll", workspace="ws", lakehouse="lh", schema="dbo").endswith("/Tables/dbo/src_dbo_payroll")


def test_case_applies_to_the_whole_name_and_upper_works():
    with _settings(SOURCE_TABLE_PREFIX="Src_", SOURCE_TABLE_CASE="upper"):
        assert physical_table("Payroll") == "SRC_PAYROLL"


def test_the_map_wins_over_prefix_and_case_and_is_used_verbatim():
    with _settings(SOURCE_TABLE_PREFIX="p_", SOURCE_TABLE_CASE="lower", SOURCE_TABLE_MAP='{"Payroll": "Pay_Roll_V2"}'):
        assert physical_table("Payroll") == "Pay_Roll_V2"
        assert physical_table("Account") == "p_account", "an unmapped table still takes the prefix and case"


def test_an_empty_schema_means_no_schema_segment():
    with _settings():
        assert table_uri("Account", workspace="ws", lakehouse="lh", schema="").endswith("/lh.Lakehouse/Tables/Account")
    with override_settings({"SOURCE_SCHEMA": ""}):
        from config_sections import parse_source_schema

        assert parse_source_schema({"SOURCE_SCHEMA": " "}, "tcc_source") == ""
        assert parse_source_schema({}, "tcc_source") == "tcc_source", "unset keeps the default"


def test_every_option_combined():
    env = {"SOURCE_TABLE_PREFIX": "x_", "SOURCE_TABLE_CASE": "lower", "SOURCE_TABLE_MAP": '{"Entity": "ent"}',
           "ONELAKE_PATH_STYLE": "guid"}
    with _settings(**env):
        assert table_uri("Payroll", workspace="W", lakehouse="L", schema="") == (
            "abfss://W@onelake.dfs.fabric.microsoft.com/L/Tables/x_payroll"
        )
        assert table_uri("Entity", workspace="W", lakehouse="L", schema="dbo").endswith("/L/Tables/dbo/ent")


@pytest.mark.parametrize("env", [
    {"SOURCE_TABLE_CASE": "title"}, {"ONELAKE_PATH_STYLE": "path"}, {"SOURCE_TABLE_MAP": "[1]"},
    {"SOURCE_TABLE_MAP": "{"}, {"SOURCE_TABLE_MAP": '{"Payroll": 3}'}, {"ONELAKE_ENDPOINT": "host-only"},
])
def test_a_bad_setting_is_refused_rather_than_guessed(env):
    from config import load_settings

    with pytest.raises(ValueError):
        load_settings(env).data_source


@pytest.mark.parametrize("name", ["a/b", "x]; DROP TABLE t;--", "", "has space"])
def test_a_physical_name_that_is_not_an_identifier_never_reaches_a_path_or_statement(name):
    with _settings(SOURCE_TABLE_MAP='{"Payroll": %s}' % __import__("json").dumps(name)):
        with pytest.raises(ValueError):
            physical_table("Payroll")


# ------------------------------------------------------- storage options


def test_the_options_carry_no_endpoint_unless_one_is_set():
    with _settings():
        assert storage_options("tok") == {"bearer_token": "tok", "use_fabric_endpoint": "true"}


def test_the_private_blob_endpoint_is_passed_as_azure_endpoint_and_transport_merges_in():
    with _settings(ONELAKE_ENDPOINT="https://abc.zab.blob.fabric.microsoft.com/"):
        options = storage_options("tok", {"connect_timeout": "60s"})
    assert options["azure_endpoint"] == "https://abc.zab.blob.fabric.microsoft.com", "no trailing slash"
    assert options["connect_timeout"] == "60s" and options["bearer_token"] == "tok"
    assert "allow_http" not in options


def test_the_helper_never_logs_a_token(caplog):
    with caplog.at_level("DEBUG"), _settings(ONELAKE_ENDPOINT="https://x.zab.blob.fabric.microsoft.com"):
        storage_options("SECRET-TOKEN-VALUE")
        table_uri("Payroll", workspace="ws", lakehouse="lh")
    assert "SECRET-TOKEN-VALUE" not in caplog.text


def test_the_writer_and_the_reader_share_one_builder():
    from data.source import from_fabric, to_delta

    assert to_delta.table_uri is from_fabric.table_uri is onelake.table_uri


# ------------------------------------------- the request deltalake really makes


@pytest.fixture
def local_endpoint():
    seen: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(404)
            self.end_headers()

        do_HEAD = do_GET

        def log_message(self, *_args):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()


def _open(uri: str, options: dict[str, str]) -> None:
    from deltalake import DeltaTable

    options = {**options, "max_retries": "0", "retry_timeout": "3s"}
    with pytest.raises(OSError):
        DeltaTable(uri, storage_options=options)


_WS, _ITEM = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))


@pytest.mark.parametrize("style,workspace,item,container,prefix", [
    ("name", "my-ws", "my-lh", "my-ws", "my-lh.Lakehouse/Tables/dbo/src_payroll/"),
    ("guid", _WS, _ITEM, _WS, f"{_ITEM}/Tables/dbo/src_payroll/"),
])
def test_the_endpoint_option_redirects_the_blob_listing_for_each_path_style(local_endpoint, style, workspace, item, container, prefix):
    endpoint, seen = local_endpoint
    with _settings(ONELAKE_ENDPOINT=endpoint, ONELAKE_PATH_STYLE=style, SOURCE_TABLE_PREFIX="src_",
                   SOURCE_TABLE_CASE="lower"):
        uri = table_uri("Payroll", workspace=workspace, lakehouse=item, schema="dbo")
        _open(uri, storage_options("dummy-token"))
    assert seen, "deltalake never reached the private endpoint"
    from urllib.parse import unquote

    paths = [unquote(p) for p in seen]
    assert all(p.startswith(f"/{container}") for p in paths), paths
    assert any(prefix in p or prefix.rstrip("/") in p for p in paths), paths


# ------------------------------------------------------------------ SQL


class _Sql(SourceSqlReader):
    def __init__(self, schema="tcc_source"):
        super().__init__(connection=object(), schema=schema)
        self.statements: list[str] = []

    def _query(self, sql, params):
        self.statements.append(" ".join(sql.split()))
        return []


def _statements(reader: _Sql) -> str:
    from infrastructure.persistence import source_sql

    source_sql.clear_cache()
    reader.list_accounts()
    reader.payroll_scope(1)
    reader.footprint()
    reader.fiscal_year_rules(1)
    return " | ".join(reader.statements)


@pytest.fixture(autouse=True)
def _clear_sql_caches():
    from infrastructure.persistence import source_sql

    source_sql.clear_cache()
    yield
    source_sql.clear_cache()


def test_the_sql_names_tables_as_it_always_did_when_nothing_is_set():
    with _settings():
        sql = _statements(_Sql())
    for table in ("Account", "Payroll", "Location", "Address", "StateCountyZip", "EntityFiscalYearRules", "Entity"):
        assert f"[lh].[tcc_source].[{table}]" in sql


def test_the_sql_uses_the_physical_names_and_an_empty_schema_uses_the_default_schema():
    with _settings(SOURCE_TABLE_PREFIX="src_dbo_", SOURCE_TABLE_CASE="lower"):
        assert "[lh].[dbo].[src_dbo_payroll]" in _statements(_Sql(schema="dbo"))
    with _settings(SOURCE_TABLE_PREFIX="src_dbo_", SOURCE_TABLE_CASE="lower"):
        sql = _statements(_Sql(schema=""))
    assert "[lh]..[src_dbo_payroll]" in sql and "[lh]..[src_dbo_entityfiscalyearrules]" in sql
    assert "[Payroll]" not in sql


def test_the_sql_honours_the_map():
    with _settings(SOURCE_TABLE_MAP='{"Payroll": "pay_v2"}'):
        sql = _statements(_Sql())
    assert "[lh].[tcc_source].[pay_v2]" in sql and "[lh].[tcc_source].[Location]" in sql


# ----------------------------------------------- local Delta, both layouts


@pytest.mark.parametrize("schema", ["dbo", ""])
def test_the_reader_finds_a_physically_named_table_in_either_layout(tmp_path, monkeypatch, schema):
    """A schema-enabled lakehouse has `Tables/<schema>/<table>`; one that is not has `Tables/<table>`."""
    import pyarrow as pa
    from deltalake import write_deltalake

    from data.source import from_fabric

    with _settings(SOURCE_TABLE_PREFIX="src_dbo_", SOURCE_TABLE_CASE="lower"):
        remote = table_uri("Account", workspace="ws", lakehouse="lh", schema=schema)
        local_root = tmp_path / "Tables"
        relative = remote.split("/Tables/", 1)[1]
        write_deltalake(str(local_root / relative), pa.table({"AccountId": [7], "Name": ["Acme"]}))

        def local(table, *, workspace, lakehouse, schema):
            return str(local_root / table_uri(table, workspace=workspace, lakehouse=lakehouse, schema=schema).split("/Tables/", 1)[1])

        monkeypatch.setattr(from_fabric, "table_uri", local)
        monkeypatch.setattr(from_fabric.FabricLakehouseReader, "_storage_options", lambda self: {})
        from_fabric.clear_cache()
        reader = from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema=schema)
        accounts = reader.list_accounts()
        from_fabric.clear_cache()
    assert accounts == [{"AccountId": 7, "Name": "Acme"}]
