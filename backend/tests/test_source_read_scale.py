"""Source reads scale with the account, not the table. [08]

A request for one account must read that account's rows (and the dimension rows they reference), never a whole
`Employment`, `Address` or `Payroll` table. These tests pin that with the read counters, and cover the cache that bounds
memory, single-flight, the negative cache for unknown ids, change detection by Delta version and the size guard.
"""
from __future__ import annotations

import ast
import dataclasses
import threading
from pathlib import Path

import pytest
from deltalake import write_deltalake
from local_lakehouse import use_local_lakehouse

from application.errors import AccountTooLarge
from data.source import build_lake, from_fabric, mapping, read_stats
from data.source.scale import generate
from data.source.to_bcs import source_to_bcs_rows

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def datasets():
    return generate(8, 8000, seed=21)


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


def _smallest(datasets):
    return min(datasets, key=lambda d: len(d.payroll))


# ---------------------------------------------------------------- reads are bounded by the account

def test_a_small_account_reads_its_own_rows_and_not_the_whole_dimension_tables(lake, datasets):
    small = _smallest(datasets)
    _reader().for_account(small.account.account_id)
    tables = read_stats.snapshot()["tables"]
    assert tables["Payroll"]["rows"] == len(small.payroll)
    assert tables["Employment"]["rows"] == len(small.employments), "Employment was read in full (every account's employees)"
    assert tables["Address"]["rows"] == len(small.addresses), "Address was read in full"
    assert tables["StateCountyZip"]["rows"] <= len(small.state_county_zips) + 12
    assert all(t["unfiltered_reads"] == 0 for name, t in tables.items() if name in ("Payroll", "Employment", "Address", "Location", "Entity"))


def test_the_rows_that_come_back_are_exactly_what_the_full_read_gave(lake, datasets):
    target = datasets[3]
    read = _reader().bcs_rows(target.account.account_id)
    # the state/county dimension is shared by every account in the lake; the generator ships it with the first account
    expected = source_to_bcs_rows(dataclasses.replace(target, state_county_zips=datasets[0].state_county_zips))
    assert read == expected, "pushdown and projection lost or changed nothing the engine reads"


def test_only_the_engines_columns_are_read(lake, datasets):
    _reader().for_account(_smallest(datasets).account.account_id)
    wanted = len(mapping.engine_fields("Payroll")) + 0
    assert read_stats.snapshot()["tables"]["Payroll"]["max_columns"] == wanted, "audit columns were read"


def test_every_unknown_id_is_remembered_and_costs_one_tiny_read_once(lake):
    reader = _reader()
    assert reader.for_account(999_999_999) is None
    after_first = read_stats.snapshot()
    assert reader.for_account(999_999_999) is None
    after_second = read_stats.snapshot()
    assert after_first["tables"].keys() == {"Account"}, "an unknown id is found out from the tiny Account read, before anything else"
    assert after_second["rows"] == after_first["rows"] and after_second["cache"]["negative_hits"] == 1


def test_the_portfolio_view_of_the_source_reads_no_payroll(lake, datasets):
    assert len(_reader().list_accounts()) == len(datasets)
    assert "Payroll" not in read_stats.snapshot()["tables"]


# ---------------------------------------------------------------- the cache

def test_a_second_request_for_an_account_is_a_cache_hit_and_reads_nothing(lake, datasets):
    reader, target = _reader(), datasets[2].account.account_id
    reader.for_account(target)
    before = read_stats.snapshot()
    reader.for_account(target)
    after = read_stats.snapshot()
    assert after["rows"] == before["rows"] and after["cache"]["hits"] == before["cache"]["hits"] + 1


def test_the_cache_is_bounded_by_entries(lake, datasets, monkeypatch):
    monkeypatch.setenv("SOURCE_CACHE_ACCOUNTS", "2")
    from_fabric.clear_cache()
    reader = _reader()
    for d in datasets[:4]:
        reader.for_account(d.account.account_id)
    assert len(from_fabric._dataset_cache()) == 2 and read_stats.snapshot()["cache"]["evictions"] == 2


def test_the_cache_is_bounded_by_an_estimated_memory_budget(lake, datasets, monkeypatch):
    monkeypatch.setenv("SOURCE_CACHE_MB", "16")
    from_fabric.clear_cache()
    cache = from_fabric._dataset_cache()
    assert cache.max_bytes == 16_000_000
    reader = _reader()
    for d in datasets:
        reader.for_account(d.account.account_id)
    assert cache.total_bytes() <= 16_000_000 or len(cache) == 1, "the budget evicts, except it never evicts the one entry just loaded"


def test_concurrent_requests_for_one_account_share_one_read(lake, datasets):
    reader, target = _reader(), datasets[4].account.account_id
    results, errors = [], []

    def work():
        try:
            results.append(reader.for_account(target))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(results) == 8 and all(r is results[0] for r in results)
    assert read_stats.snapshot()["tables"]["Payroll"]["reads"] == 1, "eight requests, one read of the account's payroll"


def test_a_failed_shared_read_fails_every_waiter_and_is_not_cached(lake, datasets, monkeypatch):
    reader, target = _reader(), datasets[1].account.account_id
    original = from_fabric.FabricLakehouseReader._scan
    calls = []

    def flaky(self, *a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("timed out")
        return original(self, *a, **k)

    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "_scan", flaky)
    with pytest.raises(OSError):
        reader.for_account(target)
    assert reader.for_account(target) is not None, "the failure was not remembered as an answer"


# ---------------------------------------------------------------- change detection

def test_a_reloaded_lake_is_noticed_and_only_that_account_is_read_again(lake, datasets, monkeypatch):
    monkeypatch.setenv("SOURCE_VERSION_CHECK_SECONDS", "1")
    from_fabric.clear_cache()
    reader = _reader()
    a, b = datasets[0].account.account_id, datasets[1].account.account_id
    first_a = reader.for_account(a)
    reader.for_account(b)
    path = lake / "Tables" / "tcc_source" / "Payroll"
    from deltalake import DeltaTable

    table = DeltaTable(str(path)).to_pyarrow_table()
    write_deltalake(str(path), table, mode="overwrite", partition_by=["AccountId"])
    for key in list(from_fabric._VERSIONS):
        stamp, version = from_fabric._VERSIONS[key]
        from_fabric._VERSIONS[key] = (stamp - 10, version)
    read_stats.reset()
    second_a = reader.for_account(a)
    assert second_a is not first_a and len(second_a.payroll) == len(first_a.payroll), "the new version was read"
    assert read_stats.snapshot()["tables"]["Payroll"]["rows"] == len(first_a.payroll), "only account a was read again"
    stale = [k for k in from_fabric._dataset_cache().keys() if k[3] == a]
    assert len(stale) == 1, "the superseded version of the account was dropped"


# ---------------------------------------------------------------- the size guard

def test_an_account_beyond_the_configured_size_is_a_typed_refusal_not_an_out_of_memory(lake, datasets, monkeypatch):
    largest = max(datasets, key=lambda d: len(d.payroll))
    monkeypatch.setenv("SOURCE_MAX_ACCOUNT_ROWS", "1000")
    with pytest.raises(AccountTooLarge) as caught:
        _reader().for_account(largest.account.account_id)
    assert caught.value.rows == len(largest.payroll) and "SOURCE_MAX_ACCOUNT_ROWS" in caught.value.remedy
    assert _reader().for_account(_smallest(datasets).account.account_id) is not None


# ---------------------------------------------------------------- the regression guard

def test_no_production_code_reads_a_delta_table_without_going_through_the_one_filtered_scan():
    """The only unfiltered `to_pyarrow_table` calls are the scan (which always filters or projects) and the local build's reconciliation."""
    sites = set()
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith(("tests/", ".venv/", "tools/")) or "/.venv/" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "to_pyarrow_table":
                        sites.add(f"{rel}::{fn.name}")
    assert sites <= {"data/source/from_fabric.py::_scan", "data/source/build_lake.py::read_back", "data/source/mapping/local.py::local_schemas",
                      "data/source/from_fabric.py::silver_rows", "data/source/silver_build.py::built_versions"}, sites


def test_the_scan_always_passes_filters_and_columns():
    source = (BACKEND / "data/source/from_fabric.py").read_text(encoding="utf-8")
    call = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "to_pyarrow_table")
    assert {k.arg for k in call.keywords} == {"columns", "filters"}


def test_the_counters_say_what_was_read():
    read_stats.reset()
    read_stats.record_read("T", 10, 100, 3, 0.5, filtered=False)
    read_stats.record_cache("hits")
    snap = read_stats.snapshot()
    assert snap["tables"]["T"]["unfiltered_reads"] == 1 and snap["rows"] == 10 and snap["cache"]["hits"] == 1
