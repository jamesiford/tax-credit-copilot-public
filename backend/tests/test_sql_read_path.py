"""The SQL-endpoint read path (`SOURCE_READ_MODE=sql`) is a spike: it must give the OneLake path's answer exactly. [10]

The endpoint is emulated (`sql_endpoint_fake.py`, SQLite behind the ODBC types), so these tests pin what this
repository controls: the statements sent, the parameter ceiling, streaming, the absent-table and size guards, that
no storage token is ever asked for, that the default mode is untouched, and that for the generated accounts both
modes yield identical datasets, engine rows and engine results. They cannot say how fast the real endpoint is, how it
spells types, or how fresh its metadata is: those are the live checks.
"""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from local_lakehouse import use_local_lakehouse
from sql_endpoint_fake import FakeLakehouseSql

from application.errors import AccountTooLarge
from config import get_settings
from data.source import build_lake, from_fabric, sql_scan
from data.source.scale import generate
from data.source.to_bcs import source_to_bcs_rows
from domain.calculation.onezero import run_min_max_method, run_pay_period_method


@pytest.fixture(scope="module")
def sample():
    return generate(6, 3000, seed=11)


@pytest.fixture
def lake(tmp_path, sample, monkeypatch):
    monkeypatch.setenv("PAY_CODE_POLICY", "assume")
    build_lake.build_local(sample, tmp_path, schema="dbo")
    return tmp_path


def _reader():
    return from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="dbo")


@pytest.fixture
def endpoint(lake, monkeypatch):
    fake = FakeLakehouseSql(lake)
    monkeypatch.setattr(sql_scan, "_connection", lambda: fake)
    return fake


def _read(monkeypatch, mode: str, account: int):
    monkeypatch.setenv("SOURCE_READ_MODE", mode)
    from_fabric.clear_cache()
    return _reader().for_account(account)


def test_the_default_read_mode_is_onelake_and_the_spike_is_opt_in(monkeypatch):
    monkeypatch.delenv("SOURCE_READ_MODE", raising=False)
    assert get_settings().source_model.read_mode == "onelake" and sql_scan.read_mode() == "onelake"
    monkeypatch.setenv("SOURCE_READ_MODE", "sql")
    assert sql_scan.read_mode() == "sql"
    monkeypatch.setenv("SOURCE_READ_MODE", "odbc")
    with pytest.raises(ValueError, match="SOURCE_READ_MODE"):
        sql_scan.read_mode()


def test_both_modes_return_identical_datasets_for_every_generated_account(lake, endpoint, sample, monkeypatch):
    use_local_lakehouse(monkeypatch, lake)
    for dataset in sample:
        account = dataset.account.account_id
        onelake = _read(monkeypatch, "onelake", account)
        sql = _read(monkeypatch, "sql", account)
        assert dataclasses.asdict(sql) == dataclasses.asdict(onelake), f"account {account}: the SQL read differs from the OneLake read"
    from_fabric.clear_cache()


def test_both_modes_project_identical_engine_rows_in_the_same_order(lake, endpoint, sample, monkeypatch):
    use_local_lakehouse(monkeypatch, lake)
    account = sample[1].account.account_id
    onelake = source_to_bcs_rows(_read(monkeypatch, "onelake", account))
    sql = source_to_bcs_rows(_read(monkeypatch, "sql", account))
    assert sql == onelake and len(sql) > 0
    from_fabric.clear_cache()


def test_the_certified_methods_give_the_same_answer_from_both_modes(lake, endpoint, sample, monkeypatch):
    """The engine reads rows, so equal rows are equal results; this runs both methods anyway, as the re-certification will."""
    from tests.certified_synthetic import certified_synthetic_pack

    use_local_lakehouse(monkeypatch, lake)
    account = sample[0].account.account_id
    answers = {}
    for mode in ("onelake", "sql"):
        rows = [r for r in source_to_bcs_rows(_read(monkeypatch, mode, account)) if r["Tax_Year"] == 2024]
        common = {"tax_year": 2024, "analysis_start_month": date(2024, 1, 1), "pack": certified_synthetic_pack(), "fiscal_window": (date(2024, 1, 1), date(2024, 12, 31))}
        mm, pp = run_min_max_method(rows, **common), run_pay_period_method(rows, **common)
        answers[mode] = (mm.annual_average, sorted(r["Employee_ID"] for r in mm.eligible_employees), pp.annual_average, sorted(r["Employee_ID"] for r in pp.eligible_employees))
    assert answers["sql"] == answers["onelake"]
    from_fabric.clear_cache()


def test_an_unknown_account_is_none_in_both_modes(lake, endpoint, monkeypatch):
    use_local_lakehouse(monkeypatch, lake)
    assert _read(monkeypatch, "sql", 999_999_999) is None and _read(monkeypatch, "onelake", 999_999_999) is None
    from_fabric.clear_cache()


def test_the_sql_path_never_asks_for_a_storage_token_or_a_delta_file(lake, endpoint, sample, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the SQL read path must not touch OneLake")

    class NoDelta:
        def __init__(self, *a, **k):
            refuse()

        is_deltatable = staticmethod(refuse)

    monkeypatch.setattr(from_fabric, "_storage_token", refuse)
    monkeypatch.setattr("deltalake.DeltaTable", NoDelta)
    monkeypatch.setenv("SOURCE_READ_MODE", "sql")
    from_fabric.clear_cache()
    dataset = _reader().for_account(sample[1].account.account_id)
    assert dataset is not None and dataset.payroll
    from_fabric.clear_cache()


def test_a_tenant_read_is_one_projected_filtered_statement_and_never_select_star(lake, endpoint, sample, monkeypatch):
    use_local_lakehouse(monkeypatch, lake)
    endpoint.reset_counters()
    _read(monkeypatch, "sql", sample[1].account.account_id)
    payroll = [s for s, _ in endpoint.statements if "payroll" in s.lower() and "INFORMATION_SCHEMA" not in s]
    assert payroll and all("*" not in s and "WHERE [" in s and "= ?" in s for s in payroll)
    from_fabric.clear_cache()


def test_a_keyed_read_batches_its_ids_under_the_parameter_ceiling(lake, endpoint, monkeypatch):
    reader = _reader()
    ids = set(range(1, 2000))
    endpoint.reset_counters()
    rows = sql_scan.scan(reader, "Address", key="address_id", ids=ids)
    keyed = [(s, p) for s, p in endpoint.statements if "IN (" in s]
    assert len(keyed) == 3 and all(len(p) <= sql_scan.ID_BATCH < 2100 for _, p in keyed)
    assert {r["address_id"] for r in rows} <= ids


def test_a_large_result_is_streamed_in_batches_not_fetched_at_once(lake, endpoint, sample, monkeypatch):
    monkeypatch.setattr(sql_scan, "FETCH_SIZE", 50)
    sizes = []
    real = type(endpoint.connect().__enter__().cursor()).fetchmany

    def counting(self, size):
        sizes.append(size)
        return real(self, size)

    monkeypatch.setattr(type(endpoint.connect().__enter__().cursor()), "fetchmany", counting)
    rows = sql_scan.scan(_reader(), "Payroll", tenant=sample[1].account.account_id)
    streamed = [s for s in sizes if s == 50]  # the column discovery uses fetchall, which is not the stream
    assert len(rows) > 50 and len(streamed) > 2


def test_an_absent_optional_table_is_no_rows_and_is_recorded_as_missing(tmp_path, sample, monkeypatch):
    from local_lakehouse import write_lakehouse

    monkeypatch.setenv("PAY_CODE_POLICY", "assume")
    write_lakehouse(tmp_path, sample[1], skip=("PayFrequency",))
    fake = FakeLakehouseSql(tmp_path)
    monkeypatch.setattr(sql_scan, "_connection", lambda: fake)
    use_local_lakehouse(monkeypatch, tmp_path)
    dataset = _read(monkeypatch, "sql", sample[1].account.account_id)
    assert "PayFrequency" in dataset.missing_tables
    from_fabric.clear_cache()


def test_an_account_beyond_the_size_limit_stops_the_read_and_is_refused(lake, endpoint, sample, monkeypatch):
    monkeypatch.setenv("SOURCE_MAX_ACCOUNT_ROWS", "1000")
    monkeypatch.setenv("SOURCE_READ_MODE", "sql")
    monkeypatch.setattr(sql_scan, "FETCH_SIZE", 100)
    biggest = max(sample, key=lambda d: len(d.payroll))
    assert len(biggest.payroll) > 1000
    from_fabric.clear_cache()
    with pytest.raises(AccountTooLarge):
        _reader().for_account(biggest.account.account_id)
    assert endpoint.rows_sent < len(biggest.payroll) + 5000, "the guard stops the stream rather than draining the table"
    from_fabric.clear_cache()


def test_column_discovery_is_asked_once_per_table_per_process_not_once_per_read(lake, endpoint, sample, monkeypatch):
    use_local_lakehouse(monkeypatch, lake)
    _read(monkeypatch, "sql", sample[1].account.account_id)
    endpoint.reset_counters()
    monkeypatch.setenv("SOURCE_READ_MODE", "sql")
    _reader().for_account(sample[2].account.account_id)
    discovery = [p for s, p in endpoint.statements if "INFORMATION_SCHEMA" in s]
    assert {t for _, t in discovery} <= {"PayFrequency", "EntityFiscalYearRules"}, "only the absent optional tables are asked about again"
    from_fabric.clear_cache()


def test_the_engine_result_does_not_depend_on_the_order_rows_arrive_in(lake, endpoint, sample, monkeypatch):
    """The endpoint promises no row order (the statement has no ORDER BY). This is what makes that safe, or says it is not."""
    import random

    from tests.certified_synthetic import certified_synthetic_pack

    use_local_lakehouse(monkeypatch, lake)
    rows = [r for r in source_to_bcs_rows(_read(monkeypatch, "sql", sample[0].account.account_id)) if r["Tax_Year"] == 2024]
    common = {"tax_year": 2024, "analysis_start_month": date(2024, 1, 1), "pack": certified_synthetic_pack(), "fiscal_window": (date(2024, 1, 1), date(2024, 12, 31))}

    def figures(ordered):
        mm, pp = run_min_max_method(ordered, **common), run_pay_period_method(ordered, **common)
        return (mm.annual_average, sorted(r["Employee_ID"] for r in mm.eligible_employees), pp.annual_average, sorted(r["Employee_ID"] for r in pp.eligible_employees))

    assert rows, "the generated account has no 2024 rows, so this would prove nothing"
    baseline = figures(rows)
    for seed in (1, 2, 3):
        shuffled = list(rows)
        random.Random(seed).shuffle(shuffled)
        assert figures(shuffled) == baseline, f"the engine's answer moved with row order (seed {seed})"
    from_fabric.clear_cache()
