"""The sample lakehouse is built in the mapping's shape, reconciled, and generated at scale deterministically. [05]

The alternate shape is `tests/alt_shape_mapping.json` (prefixed lower-case table names, the DDL's own column spellings,
narrower integer types), so the same build, reader, writer and validation are exercised against a shape that is not the
default, with no code change.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
from pathlib import Path

import pytest
from deltalake import DeltaTable

from data.source import build_lake, from_fabric, mapping
from data.source.mapping import validate
from data.source.mapping.local import local_schemas
from data.source.scale import FIRST_ACCOUNT_ID, account_sizes, generate
from data.source.to_bcs import source_to_bcs_rows

ALT = Path(__file__).resolve().parent / "alt_shape_mapping.json"
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
DEMO_IDS = {1001, 2001, 2002, 2003, 2004, 2005}


@pytest.fixture
def alt(monkeypatch):
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(ALT))
    monkeypatch.setenv("PAY_CODE_POLICY", "assume")


@pytest.fixture(scope="module")
def sample():
    return generate(6, 3000, seed=11)


def _script(name: str):
    spec = importlib.util.spec_from_file_location(Path(name).stem.replace("-", "_"), SCRIPTS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- the build

def test_the_build_lands_in_the_alternate_shape_and_reconciles_with_no_loss(alt, tmp_path, sample):
    report = build_lake.build_local(sample, tmp_path, schema="dbo")
    assert report.ok and report.reconciliation, "every table matches on rows and on a checksum of the logical values"
    payroll = DeltaTable(str(tmp_path / "Tables" / "dbo" / "alt_dbo_payroll"))
    names = {f.name: str(f.type.type) for f in payroll.schema().fields}
    assert {"Accountid", "PaycheckDate", "ClientEmployeeID"} <= set(names) and "AccountId" not in names and "PayDate" not in names
    assert names["CreatedBy"] == "integer", "an `int` column lands as int32, a `bigint` stays long"
    assert names["EmployeeId"] == "long"
    assert payroll.metadata().partition_columns == ["Accountid"], "partitioned by the tenant column, mirroring PayrollRange_PS"
    assert {r["table"] for r in report.reconciliation}.isdisjoint(build_lake.LOOKUP_TABLES)


def test_the_app_reads_the_rebuilt_lake_through_the_mapping_and_projects_every_row(alt, tmp_path, sample, monkeypatch):
    build_lake.build_local(sample, tmp_path, schema="dbo")
    from local_lakehouse import use_local_lakehouse

    use_local_lakehouse(monkeypatch, tmp_path)
    reader = from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="dbo")
    target = sample[1]
    loaded = reader.for_account(target.account.account_id)
    assert len(loaded.payroll) == len(target.payroll), "the tenant filter ran on the renamed, re-cased partition column"
    assert set(loaded.missing_tables) == {"PayFrequency", "EntityFiscalYearRules"}, "built without the app-owned lookups"
    assert len(source_to_bcs_rows(loaded)) == len(target.payroll)
    from_fabric.clear_cache()


def test_the_validation_cli_passes_the_rebuilt_lake(alt, tmp_path, sample, capsys):
    build_lake.build_local(sample, tmp_path, schema="dbo")
    cli = _script("validate-source-schema.py")
    assert cli.main(["--root", str(tmp_path), "--schema", "dbo"]) == 0
    out = capsys.readouterr().out
    assert "ERRORS" not in out and "optional table alt_dbo_payfrequency is absent" in out


def test_with_lookups_writes_them_too(alt, tmp_path, sample):
    report = build_lake.build_local(sample, tmp_path, schema="dbo", include_lookups=True)
    assert report.ok and {"PayFrequency", "EntityFiscalYearRules"} <= {r["table"] for r in report.reconciliation}


def test_a_dry_run_writes_nothing_and_says_what_it_would_do(alt, tmp_path, sample):
    report = build_lake.build_local(sample, tmp_path / "lake", schema="dbo", dry_run=True)
    assert not (tmp_path / "lake").exists() and report.dry_run and not report.reconciliation
    plan = {t.logical: t for t in report.plan}
    assert plan["Payroll"].physical == "alt_dbo_payroll" and plan["Payroll"].rows == sum(len(d.payroll) for d in sample)
    assert plan["Payroll"].partition_by == ("Accountid",) and plan["PayFrequency"].skipped


def test_a_rerun_is_idempotent_and_never_appends(alt, tmp_path, sample):
    first = build_lake.build_local(sample, tmp_path, schema="dbo")
    second = build_lake.build_local(sample, tmp_path, schema="dbo")
    assert [r["rows_after"] for r in second.reconciliation] == [r["rows_after"] for r in first.reconciliation]
    assert second.ok


def test_reconciliation_catches_a_lost_or_altered_row(alt, tmp_path, sample):
    from deltalake import write_deltalake
    import pyarrow as pa

    build_lake.build_local(sample, tmp_path, schema="dbo")
    path = tmp_path / "Tables" / "dbo" / "alt_dbo_payroll"
    table = DeltaTable(str(path)).to_pyarrow_table()
    write_deltalake(str(path), table.slice(1), mode="overwrite", partition_by=["Accountid"])
    broken = build_lake.reconcile(sample, tmp_path, "dbo", False)
    assert any(r["table"] == "Payroll" and not r["rows_match"] and not r["checksum_match"] for r in broken)
    altered = table.set_column(table.schema.get_field_index("Hours"), "Hours", pa.array([table["Hours"][0]] * table.num_rows, type=table["Hours"].type))
    write_deltalake(str(path), altered, mode="overwrite", partition_by=["Accountid"])
    assert any(r["table"] == "Payroll" and r["rows_match"] and not r["checksum_match"] for r in build_lake.reconcile(sample, tmp_path, "dbo", False))


def test_the_default_shape_also_builds_and_reconciles(tmp_path, sample):
    assert build_lake.build_local(sample, tmp_path, schema="tcc_source").ok
    assert (tmp_path / "Tables" / "tcc_source" / "Payroll").is_dir()


def test_the_data_quality_report_finds_nothing_wrong_in_clean_data_and_an_orphan_in_broken_data(sample):
    import dataclasses

    clean = build_lake.quality_report(sample)
    assert clean["duplicate_payroll_ids"] == 0 and clean["orphan_location_ids"] == 0 and clean["orphan_pay_code_ids"] == 0
    broken = [dataclasses.replace(sample[0], payroll=[dataclasses.replace(p, location_id=-5) for p in sample[0].payroll[:3]])]
    assert build_lake.quality_report(broken)["orphan_location_ids"] == 1


def test_the_build_script_refuses_an_ambiguous_target_and_an_unconfirmed_fabric_write(capsys):
    script = _script("fabric/build-sample-lakehouse.py")
    with pytest.raises(SystemExit):
        script.main([])
    with pytest.raises(SystemExit):
        script.main(["--fabric"])


def test_the_build_script_writes_a_report_and_exits_nonzero_only_on_a_mismatch(alt, tmp_path, capsys):
    script = _script("fabric/build-sample-lakehouse.py")
    report_path = tmp_path / "report.json"
    code = script.main(["--root", str(tmp_path / "lake"), "--source", "scale", "--accounts", "4", "--rows", "400", "--schema", "dbo",
                        "--report", str(report_path), "--mapping-file", str(ALT)])
    assert code == 0 and json.loads(report_path.read_text(encoding="utf-8"))["reconciled"] is True


# ---------------------------------------------------------------- the generator

def test_the_generator_is_deterministic_by_seed_and_different_for_another():
    a, b, c = generate(5, 1500, seed=3), generate(5, 1500, seed=3), generate(5, 1500, seed=4)
    assert build_lake.checksum(build_lake._dataset_rows(a, "Payroll"), mapping.spec("Payroll")) == build_lake.checksum(build_lake._dataset_rows(b, "Payroll"), mapping.spec("Payroll"))
    assert build_lake.checksum(build_lake._dataset_rows(a, "Payroll"), mapping.spec("Payroll")) != build_lake.checksum(build_lake._dataset_rows(c, "Payroll"), mapping.spec("Payroll"))


def test_the_generator_gives_exactly_n_accounts_and_m_rows_with_a_heavy_tailed_skew():
    datasets = generate(40, 20_000, seed=9)
    sizes = sorted((len(d.payroll) for d in datasets), reverse=True)
    assert len(datasets) == 40 and sum(sizes) == 20_000
    assert sizes[0] >= 5 * statistics.median(sizes), "a few very large accounts and many small ones"
    assert min(sizes) >= 1 and account_sizes(40, 20_000) == [len(d.payroll) for d in datasets]


def test_generated_accounts_are_not_demo_accounts_and_carry_no_personal_data():
    datasets = generate(8, 1200, seed=2)
    ids = {d.account.account_id for d in datasets}
    assert ids.isdisjoint(DEMO_IDS) and min(ids) == FIRST_ACCOUNT_ID
    assert all(d.account.name.startswith("Scale Account ") for d in datasets)
    forbidden = {"first_name", "last_name", "national_id", "date_of_birth", "phone", "email", "birth_date", "email_address"}
    for table, (_attr, fields) in __import__("data.source.to_delta", fromlist=["TABLE_SPECS"]).TABLE_SPECS.items():
        assert not forbidden & set(fields), table


def test_generated_ids_are_unique_across_accounts_and_keys_resolve():
    datasets = generate(12, 3000, seed=5)
    quality = build_lake.quality_report(datasets)
    assert quality["duplicate_payroll_ids"] == 0 and not quality["orphan_location_ids"] and not quality["orphan_entity_ids"]
    locations = [loc.location_id for d in datasets for loc in d.locations]
    assert len(locations) == len(set(locations))


def test_the_generator_refuses_an_impossible_request():
    with pytest.raises(ValueError):
        generate(10, 5)
    with pytest.raises(ValueError):
        generate(0, 100)


def test_the_scale_wrapper_runs_a_dry_run_without_writing(tmp_path, capsys):
    wrapper = _script("generate-synthetic-source.py")
    assert wrapper.main(["--accounts", "5", "--rows", "500", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True and plan["quality"]["payroll_rows"] == 500
    assert not list(tmp_path.iterdir())
