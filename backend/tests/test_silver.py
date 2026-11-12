"""Silver gives the engine the same rows, and so the same certified figures, as the raw path. [08.3, 08.4]"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from local_lakehouse import use_local_lakehouse

from application.errors import SilverNotBuilt, UnmappedPayCodes
from data.source import build_lake, from_fabric, mapping, read_stats
from data.source.scale import generate
from data.source.silver import finalize_pay_codes, refresh_plan
from data.source.silver_build import build_silver, built_versions
from data.lookups import store as override_store
from data.lookups.store import OverrideEntry
from infrastructure.persistence.sqlite_lookups import SqliteLookupStore

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def datasets():
    return generate(6, 6000, seed=31)


@pytest.fixture
def lake(tmp_path, monkeypatch, datasets):
    monkeypatch.setenv("PAY_CODE_POLICY", "assume")
    build_lake.build_local(datasets, tmp_path, schema="tcc_source")
    use_local_lakehouse(monkeypatch, tmp_path)
    read_stats.reset()
    yield tmp_path
    from_fabric.clear_cache()


def _reader():
    return from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="tcc_source")


def _build(reader, **kw):
    return build_silver(reader, reader._silver_uri(), mapping.column("Payroll", "account_id"), **kw)


def test_silver_rows_are_identical_to_the_raw_rows_for_every_account(lake, datasets, monkeypatch):
    reader = _reader()
    raw = {d.account.account_id: reader.bcs_rows(d.account.account_id) for d in datasets}
    _build(reader)
    from_fabric.clear_cache()
    monkeypatch.setenv("SOURCE_SILVER", "require")
    for d in datasets:
        assert _reader().bcs_rows(d.account.account_id) == raw[d.account.account_id], d.account.account_id


def test_the_engine_gives_the_same_certified_figures_from_silver(lake, datasets, monkeypatch):
    from application.assessment import assess_client

    reader = _reader()
    target = max(datasets, key=lambda d: len(d.payroll)).account.account_id
    raw = assess_client(target, reader.bcs_rows(target), program_code="GA_JTC", tax_years=[2023])
    _build(reader)
    from_fabric.clear_cache()
    monkeypatch.setenv("SOURCE_SILVER", "auto")
    silver = assess_client(target, _reader().bcs_rows(target), program_code="GA_JTC", tax_years=[2023])
    assert raw["assessed"], "something was priced, so the comparison is not vacuous"
    volatile = {"claim_id", "decided_at", "effective_from", "effective_to", "created_at"}  # a new id and clock reading per run

    def figures(result):
        return {k: v for k, v in result.items() if k != "assessed"} | {
            "assessed": [{k: v for k, v in cell.items() if k not in volatile} for cell in result["assessed"]]}

    assert figures(silver) == figures(raw)


def test_a_silver_read_touches_one_partition_and_no_source_table(lake, datasets, monkeypatch):
    reader = _reader()
    _build(reader)
    from_fabric.clear_cache()
    read_stats.reset()
    monkeypatch.setenv("SOURCE_SILVER", "require")
    small = min(datasets, key=lambda d: len(d.payroll))
    _reader().bcs_rows(small.account.account_id)
    tables = read_stats.snapshot()["tables"]
    assert set(tables) == {"Silver"} and tables["Silver"]["rows"] == len(small.payroll), "no Employment, Address or Payroll read"


def test_the_default_is_off_and_changes_nothing(lake, datasets):
    reader = _reader()
    _build(reader)
    from_fabric.clear_cache()
    read_stats.reset()
    reader.bcs_rows(datasets[0].account.account_id)
    assert "Silver" not in read_stats.snapshot()["tables"] and "Payroll" in read_stats.snapshot()["tables"]


def test_auto_falls_back_to_raw_for_an_account_with_no_partition_and_require_refuses(lake, datasets, monkeypatch):
    reader = _reader()
    first, second = datasets[0].account.account_id, datasets[1].account.account_id
    _build(reader, accounts=[first])
    from_fabric.clear_cache()
    monkeypatch.setenv("SOURCE_SILVER", "auto")
    assert len(_reader().bcs_rows(second)) == len(datasets[1].payroll)
    monkeypatch.setenv("SOURCE_SILVER", "require")
    with pytest.raises(SilverNotBuilt):
        _reader().bcs_rows(second)


def test_the_pay_code_lookup_is_applied_on_read_so_an_override_needs_no_rebuild(lake, datasets, monkeypatch):
    reader = _reader()
    target = datasets[2].account.account_id
    _build(reader)
    from_fabric.clear_cache()
    monkeypatch.setenv("SOURCE_SILVER", "require")
    monkeypatch.setenv("DATA_CLASSIFICATION", "customer")
    monkeypatch.setenv("PAY_CODE_POLICY", "strict")
    previous = override_store.get_store()
    store = SqliteLookupStore(":memory:")
    override_store.install(store)
    try:
        with pytest.raises(UnmappedPayCodes):
            _reader().bcs_rows(target)
        for code in ("REG", "OT", "BON", "PTO"):
            store.put(OverrideEntry("pay_code_category", target, "code", code, "Regular", "tester@example.com"))
        rows = _reader().bcs_rows(target)
        assert rows and not any(r["_Pay_Code_Unmapped"] for r in rows)
    finally:
        override_store.install(previous)


def test_an_unchanged_lake_is_a_no_op_and_a_changed_version_rebuilds(lake, datasets):
    reader = _reader()
    first = _build(reader)
    assert len(first["built"]) == len(datasets) and first["rows"] == sum(len(d.payroll) for d in datasets)
    second = _build(reader)
    assert second["built"] == [] and second["skipped_unchanged"] == len(datasets)
    assert len(_build(reader, force=True)["built"]) == len(datasets)
    uri, column = reader._silver_uri(), mapping.column("Payroll", "account_id")
    assert set(built_versions(uri, column).values()) == {first["source_version"]}
    assert refresh_plan({1: 4, 2: 5}, [1, 2, 3], 5) == [1, 3], "an account built from an older version, and one never built"


def test_a_refresh_replaces_only_the_named_accounts_partition(lake, datasets):
    reader = _reader()
    _build(reader)
    before = {a: v for a, v in built_versions(reader._silver_uri(), mapping.column("Payroll", "account_id")).items()}
    report = _build(reader, accounts=[datasets[0].account.account_id], force=True)
    assert report["built"] == [datasets[0].account.account_id]
    from deltalake import DeltaTable

    table = DeltaTable(reader._silver_uri()).to_pyarrow_table()
    assert table.num_rows == sum(len(d.payroll) for d in datasets), "no duplicates, nothing lost"
    assert set(before) == {d.account.account_id for d in datasets}


def test_a_dry_run_builds_nothing(lake, datasets):
    reader = _reader()
    report = _build(reader, dry_run=True)
    assert report["dry_run"] and report["built"] and built_versions(reader._silver_uri(), mapping.column("Payroll", "account_id")) == {}


def test_finalize_marks_a_defaulted_row_and_leaves_it_alone():
    row = {"Pay_Code": "Regular", "_Pay_Code_Defaulted": True, "_Pay_Code_Category_Id": None}
    assert finalize_pay_codes([row], 5, "assume")[0]["_Pay_Code_Unmapped"] is False


def test_the_build_script_runs_end_to_end_on_a_local_lake(lake, datasets, capsys):
    spec = importlib.util.spec_from_file_location("build_silver_script", SCRIPTS / "fabric" / "build-silver.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.main(["--root", str(lake), "--schema", "tcc_source", "--accounts", str(datasets[0].account.account_id)]) == 0
    assert json.loads(capsys.readouterr().out)["built"] == [datasets[0].account.account_id]
