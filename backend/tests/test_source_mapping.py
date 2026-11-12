"""Renaming a table or a column is a configuration change, not a code change. [06.7]

One temporary mapping renames a table, renames columns and changes their case. Every consumer then follows with
no edit: the writer, the reader (including its case-sensitive tenant filter), the SQL builder, the governed
data-query model and the tenant allow-list. A separate test fails if a physical name is spelled outside the mapping.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import re
from pathlib import Path

import pytest
from deltalake import DeltaTable
from local_lakehouse import use_local_lakehouse, write_lakehouse

from application.data import source_names
from data.source import from_fabric, mapping
from data.source.mapping import validate
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from data.source.to_bcs import projection_controls, source_to_bcs_rows

BACKEND = Path(__file__).resolve().parents[1]
RENAMED = {
    "version": 1,
    "naming": {"table_prefix": "zz_", "table_case": "lower"},
    "tables": {
        "Payroll": {"table": "PayRoll_Facts", "fields": {"account_id": {"column": "Accountid"}, "pay_date": {"column": "PaycheckDate"}}},
        "Location": {"fields": {"location_name": {"column": "SiteName"}}},
    },
}


@pytest.fixture(scope="module")
def dataset():
    return build_synthetic_dataset(SYNTHETIC_CLIENTS[0])


@pytest.fixture
def renamed(tmp_path, monkeypatch):
    path = tmp_path / "renamed.json"
    path.write_text(json.dumps(RENAMED), encoding="utf-8")
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(path))
    return path


@pytest.fixture
def lake(tmp_path, monkeypatch):
    use_local_lakehouse(monkeypatch, tmp_path / "lake")
    yield tmp_path / "lake"
    from_fabric.clear_cache()


def _reader():
    return from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="tcc_source")


def test_the_default_mapping_keeps_every_name_the_code_used_before():
    assert mapping.physical_table("Payroll") == "Payroll" and mapping.column("Payroll", "pay_period_start") == "PayPeriodStart"
    assert mapping.tenant_column("Payroll") == "AccountId" and mapping.partition_columns("Payroll") == ["AccountId"]


def test_a_renamed_table_and_columns_reach_the_writer(renamed, lake, dataset):
    written = write_lakehouse(lake, dataset, schema="tcc_source")
    table = DeltaTable(str(written["Payroll"]))
    names = [f.name for f in table.schema().fields]
    assert written["Payroll"].name == "zz_payroll_facts"
    assert "Accountid" in names and "PaycheckDate" in names and "AccountId" not in names and "PayDate" not in names
    assert table.metadata().partition_columns == ["Accountid"], "the partition follows the renamed tenant column"
    assert "SiteName" in [f.name for f in DeltaTable(str(written["Location"])).schema().fields]


def test_the_reader_follows_with_no_code_change(renamed, lake, dataset):
    write_lakehouse(lake, dataset, schema="tcc_source")
    loaded = _reader().for_account(dataset.account.account_id)
    assert loaded is not None and len(loaded.payroll) == len(dataset.payroll), "the tenant filter used the renamed column"
    assert [l.location_name for l in loaded.locations] == [l.location_name for l in dataset.locations]
    assert source_to_bcs_rows(loaded)


def test_a_difference_in_case_alone_does_not_break_the_filter_or_the_projection(tmp_path, monkeypatch, lake, dataset):
    """Delta filters are case-sensitive; the reader resolves the actual spelling from the table's own schema."""
    path = tmp_path / "cased.json"
    path.write_text(json.dumps({"version": 1, "tables": {"Payroll": {"fields": {"account_id": {"column": "Accountid"}}}}}), encoding="utf-8")
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(path))
    write_lakehouse(lake, dataset, schema="tcc_source")          # the lake spells it Accountid ...
    monkeypatch.delenv("SOURCE_MAPPING_FILE")                    # ... and the mapping in force says AccountId
    from_fabric.clear_cache()
    loaded = _reader().for_account(dataset.account.account_id)
    assert loaded is not None and len(loaded.payroll) == len(dataset.payroll)


def test_the_sql_builder_follows(renamed):
    from infrastructure.persistence import source_queries as q

    sql = q.payroll_scope(lambda logical: f"[lh].[s].[{mapping.physical_table(logical)}]")
    assert "p.[Accountid] = ?" in sql and "p.[PaycheckDate]" in sql and "[zz_payroll_facts]" in sql
    assert "[AccountId]" not in sql and "[PayDate]" not in sql
    assert "[Accountid]" in q.footprint(lambda logical: logical)


def test_the_data_query_model_follows(renamed):
    from application.data.model_source import source_datasets
    from bootstrap.data_wiring import install_source_names

    install_source_names()
    payroll, location, _ = source_datasets()
    assert payroll.table == "zz_payroll_facts" and payroll.tenant_column == "Accountid"
    assert payroll.column("pay_date").physical == "PaycheckDate" and location.column("location_name").physical == "SiteName"
    assert "PaycheckDate" in payroll.column("pay_year").depends_on
    assert "[PayDate]" not in payroll.column("pay_year").expression[0]
    assert source_names.tenant_column("Payroll") == "Accountid"


def test_the_tenant_allow_list_follows_the_mapping(renamed):
    from infrastructure.persistence.tenant_sql import TenantScopedQuery, TenantScopeViolation

    sql, params = TenantScopedQuery(7).bind("SELECT 1 FROM t WHERE {tenant:t@Accountid} AND t.x = ?", [1])
    assert "t.Accountid = ?" in sql and params == [7, 1]
    with pytest.raises(TenantScopeViolation):
        TenantScopedQuery(7).bind("SELECT 1 FROM t WHERE {tenant:t@PaycheckDate}", [])


def test_the_grants_name_the_physical_tables(renamed):
    from application.data.semantic_model import Source
    from bootstrap.data_wiring import install_source_names
    from application.data.semantic_model import default_model

    install_source_names()
    tables = {d.table for d in default_model().datasets if d.source is Source.LAKEHOUSE}
    assert "zz_payroll_facts" in tables and "Payroll" not in tables


def test_a_field_the_engine_does_not_know_is_refused_at_load(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": 1, "tables": {"Payroll": {"fields": {"shift_bonus": {"column": "ShiftBonus", "type": "int64"}}}}}), encoding="utf-8")
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(path))
    with pytest.raises(mapping.MappingError, match="needs\\s+code"):
        mapping.mapping()


@pytest.mark.parametrize("patch", [
    {"Payroll": {"drop_fields": ["pay_period_start"]}},
    {"Payroll": {"fields": {"hours": {"column": "Hours; DROP TABLE x"}}}},
    {"Payroll": {"fields": {"hours": {"type": "varchar"}}}},
])
def test_a_malformed_or_unsafe_mapping_is_refused(tmp_path, monkeypatch, patch):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": 1, "tables": patch}), encoding="utf-8")
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(path))
    with pytest.raises(mapping.MappingError):
        mapping.mapping()


# ---------------------------------------------------------------- validation report

def _actual(**changes):
    """The default mapping's own columns as a lake carrying them, with `changes` applied."""
    schema = {t: {m.column: _delta(m.type) for m in table.fields.values()} for t, table in mapping.mapping().tables.items()}
    for table, edit in changes.items():
        schema[table] = None if edit is None else edit(dict(schema[table]))
    return schema


def _delta(arrow: str) -> str:
    return {"int64": "long", "string": "string", "bool": "boolean", "double": "double", "date32": "date",
            "timestamp[us]": "timestamp"}.get(arrow, "decimal(18,2)")


def _report(actual):
    current = mapping.mapping()
    return validate.validate(current, actual, {t: mapping.physical_table(t) for t in current.tables})


def test_a_lake_that_matches_the_mapping_is_ok():
    assert _report(_actual()).status == "ok"


def test_a_missing_required_column_is_an_error_naming_it():
    report = _report(_actual(Payroll=lambda c: {k: v for k, v in c.items() if k != "PayPeriodStart"}))
    assert report.status == "error" and any("Payroll: no column for required field pay_period_start" in e for e in report.errors)


def test_a_missing_required_table_is_an_error_and_a_missing_optional_one_a_warning():
    report = _report(_actual(Payroll=None, Employment=None))
    assert any("Payroll: table Payroll is absent" in e for e in report.errors)
    assert any("optional table Employment is absent" in w for w in report.warnings) and not any("Employment" in e for e in report.errors)


def test_a_missing_optional_field_a_case_difference_and_an_extra_column_are_warnings():
    def edit(columns):
        columns["Accountid"] = columns.pop("AccountId")
        columns.pop("HourlyRate")
        columns["Union"] = "string"
        return columns

    report = _report(_actual(Payroll=edit))
    assert report.status == "warning" and not report.errors
    text = "\n".join(report.warnings)
    assert "no column for optional field hourly_rate" in text and "'Accountid', mapped as 'AccountId'" in text and "'Union' is not mapped" in text


def test_a_retyped_column_is_read_with_coercion_when_it_can_be_and_an_error_when_it_cannot():
    report = _report(_actual(Payroll=lambda c: {**c, "HourlyRate": "string", "PayrollId": "date"}))
    assert any("hourly_rate: stored as string, mapped as decimal128(18, 2); read with coercion" in w for w in report.warnings)
    assert not any("hourly_rate" in e for e in report.errors)
    report = _report(_actual(Payroll=lambda c: {**c, "PayPeriodStart": "string"}))
    assert any("pay_period_start: stored as string, cannot be read as date32" in e for e in report.errors)


def test_a_lake_on_disk_is_validated_end_to_end(tmp_path, dataset):
    from data.source.mapping.local import local_schemas

    write_lakehouse(tmp_path, dataset, schema="tcc_source")
    assert _report(local_schemas(tmp_path, "tcc_source")).status in {"ok", "warning"} and not _report(local_schemas(tmp_path, "tcc_source")).errors
    assert _report(local_schemas(tmp_path / "nowhere", "tcc_source")).errors


def test_a_required_column_the_lake_lacks_is_a_named_error_at_read_time(tmp_path, monkeypatch, lake, dataset):
    write_lakehouse(lake, dataset, schema="tcc_source")
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"version": 1, "tables": {"Payroll": {"fields": {"pay_period_end": {"column": "PeriodStops"}}}}}), encoding="utf-8")
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(path))
    from application.errors import SourceSchemaMismatch

    with pytest.raises(SourceSchemaMismatch) as caught:
        _reader().for_account(dataset.account.account_id)
    assert caught.value.missing == ("pay_period_end",) and "validate-source-schema.py" in caught.value.remedy


# ---------------------------------------------------------------- named transforms

def _with_null_pay_dates(dataset, count=3):
    rows = [dataclasses.replace(p, pay_date=None) if i < count else p for i, p in enumerate(dataset.payroll)]
    return dataclasses.replace(dataset, payroll=rows)


def test_a_null_paycheck_date_is_imputed_counted_and_flagged_never_a_crash(dataset):
    broken = _with_null_pay_dates(dataset)
    rows = source_to_bcs_rows(broken)
    assert len(rows) == len(dataset.payroll)
    imputed = [r for r in rows if r["_Pay_Date_Imputed"]]
    assert len(imputed) == 3 and all(r["Pay_Date"] == r["Pay_Period_End"] for r in imputed)
    controls = projection_controls(broken, rows)
    assert controls["null_pay_date"] == 3 and controls["null_pay_date_imputed"] == 3 and controls["null_pay_date_excluded"] == 0


def test_the_exclude_policy_leaves_the_rows_out_and_counts_them(dataset, monkeypatch):
    monkeypatch.setenv("NULL_PAY_DATE_POLICY", "exclude")
    broken = _with_null_pay_dates(dataset)
    rows = source_to_bcs_rows(broken)
    assert len(rows) == len(dataset.payroll) - 3
    controls = projection_controls(broken, rows)
    assert controls["null_pay_date_excluded"] == 3 and controls["null_pay_date_imputed"] == 0 and controls["null_pay_date_policy"] == "exclude"


@pytest.mark.parametrize("mode", ["worksite_then_location", "location_only", "worksite_only"])
def test_the_worksite_transform_has_a_python_and_a_sql_form_that_agree(mode):
    from data.source.mapping import transforms

    assert transforms.worksite_id(mode, 5, 9) == {"worksite_then_location": 5, "location_only": 9, "worksite_only": 5}[mode]
    assert transforms.worksite_id(mode, None, 9) == {"worksite_then_location": 9, "location_only": 9, "worksite_only": None}[mode]
    sql = transforms.worksite_sql(mode, "W", "L")
    assert {"worksite_then_location": "COALESCE(W, L)", "location_only": "L", "worksite_only": "W"}[mode] == sql


def test_an_unknown_transform_is_refused(monkeypatch):
    monkeypatch.setenv("WORKSITE_LOCATION_SOURCE", "sometimes")
    with pytest.raises(ValueError):
        from config import get_settings

        get_settings().source_model


def test_a_stringly_typed_hourly_wage_and_a_junk_value_coerce_safely():
    from decimal import Decimal

    assert from_fabric._coerce("21.50 ", "decimal128(18, 2)") == Decimal("21.50")
    assert from_fabric._coerce("$1,020.10", "decimal128(18, 2)") == Decimal("1020.10")
    assert from_fabric._coerce("n/a", "decimal128(18, 2)") is None and from_fabric._coerce("", "decimal128(18, 2)") is None


def test_a_reserved_word_column_is_quoted(tmp_path, monkeypatch):
    path = tmp_path / "reserved.json"
    path.write_text(json.dumps({"version": 1, "tables": {"Location": {"fields": {"dba": {"column": "union"}}}}}), encoding="utf-8")
    monkeypatch.setenv("SOURCE_MAPPING_FILE", str(path))
    assert mapping.quoted("Location", "dba", "l") == "l.[union]"


# ---------------------------------------------------------------- the literal guard

#: Modules that touch the lake's names. A physical COLUMN is spelled in the mapping and nowhere else here.
GUARDED = [
    "data/source/from_fabric.py", "data/source/to_delta.py", "data/source/to_bcs.py", "data/source/load_fabric.py",
    "infrastructure/persistence/source_sql.py", "infrastructure/persistence/source_queries.py",
    "infrastructure/persistence/footprint_guard.py", "infrastructure/persistence/tenant_sql.py",
    "infrastructure/persistence/tenant_marker.py", "application/data/model_source.py",
    "application/data/model_dsl.py", "bootstrap/data_wiring.py",
]
CAMEL = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+$")


def _strings(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            yield node.lineno, node.value


def test_no_physical_column_is_spelled_outside_the_mapping():
    columns = {m.column for t in mapping.default_mapping().tables.values() for m in t.fields.values() if CAMEL.match(m.column)}
    columns -= set(mapping.default_mapping().tables)  # PayCode is a logical table name and also a column of it
    pattern = re.compile(r"\b(" + "|".join(sorted(columns, key=len, reverse=True)) + r")\b")
    breaches = []
    for rel in GUARDED:
        for line, text in _strings(BACKEND / rel):
            if pattern.search(text):
                breaches.append(f"{rel}:{line}: {text[:60]!r}")
    assert not breaches, "a physical column name is written in code instead of read from the mapping:\n" + "\n".join(breaches)
