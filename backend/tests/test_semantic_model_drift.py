"""The semantic model must agree with the schema the repo defines, and say so when it does not. [CH-16a]

The model is a promise about what exists. A column added to the DDL without a decision
would be silently unqueryable (or worse, queryable without a sensitivity ruling), so this
fails the build until the column is modelled, blocked or excluded with a reason.
"""
from __future__ import annotations

import pytest

from application.data.model_excluded import EXCLUDED_SOURCE_TABLES, EXCLUDED_WAREHOUSE_TABLES
from application.data.semantic_model import Dataset, Source, default_model
from tests.ddl_schema import parse_ddl, source_tables, warehouse_tables

MODEL = default_model()


def _physical(dataset: Dataset) -> list[str]:
    if dataset.source is Source.WAREHOUSE:
        return warehouse_tables()[f"tcc_{dataset.schema.value}.{dataset.table}"]
    return source_tables()[dataset.table]


def undecided_columns(dataset: Dataset, physical: list[str]) -> set[str]:
    """Columns the table has that the dataset neither models, blocks nor excludes."""
    return set(physical) - dataset.physical_columns()


def invented_columns(dataset: Dataset, physical: list[str]) -> set[str]:
    """Columns the dataset names that the table does not have."""
    return dataset.physical_columns() - set(physical)


@pytest.mark.parametrize("dataset", MODEL.datasets, ids=lambda d: d.name)
def test_every_physical_column_is_decided(dataset):
    assert not undecided_columns(dataset, _physical(dataset)), (
        f"{dataset.name}: columns in the schema with no decision. Model them (blocked if they could "
        "identify a person) or add them to excluded_columns with a reason."
    )


@pytest.mark.parametrize("dataset", MODEL.datasets, ids=lambda d: d.name)
def test_no_modelled_column_is_invented(dataset):
    assert not invented_columns(dataset, _physical(dataset))


def test_every_warehouse_table_is_modelled_or_excluded_with_a_reason():
    modelled = {f"tcc_{d.schema.value}.{d.table}" for d in MODEL.datasets if d.source is Source.WAREHOUSE}
    undecided = set(warehouse_tables()) - modelled - set(EXCLUDED_WAREHOUSE_TABLES)
    assert not undecided, f"tables with no decision: {sorted(undecided)}"
    assert all(reason.strip() for reason in EXCLUDED_WAREHOUSE_TABLES.values())


def test_every_source_table_is_modelled_or_excluded_with_a_reason():
    modelled = {d.table for d in MODEL.datasets if d.source is Source.LAKEHOUSE}
    undecided = set(source_tables()) - modelled - set(EXCLUDED_SOURCE_TABLES)
    assert not undecided, f"source tables with no decision: {sorted(undecided)}"
    assert all(reason.strip() for reason in EXCLUDED_SOURCE_TABLES.values())


def test_the_exclusion_lists_name_real_tables_and_never_a_modelled_one():
    modelled_wh = {f"tcc_{d.schema.value}.{d.table}" for d in MODEL.datasets if d.source is Source.WAREHOUSE}
    modelled_src = {d.table for d in MODEL.datasets if d.source is Source.LAKEHOUSE}
    assert set(EXCLUDED_WAREHOUSE_TABLES) <= set(warehouse_tables())
    assert set(EXCLUDED_SOURCE_TABLES) <= set(source_tables())
    assert not set(EXCLUDED_WAREHOUSE_TABLES) & modelled_wh
    assert not set(EXCLUDED_SOURCE_TABLES) & modelled_src


def test_every_excluded_column_has_a_reason():
    for dataset in MODEL.datasets:
        assert all(reason.strip() for _, reason in dataset.excluded_columns), dataset.name


def test_every_warehouse_gold_table_with_a_client_key_is_decided():
    gold = {t for t, cols in warehouse_tables().items() if t.startswith("tcc_gold.") and "client_id" in cols}
    modelled = {f"tcc_{d.schema.value}.{d.table}" for d in MODEL.datasets}
    assert gold <= modelled | set(EXCLUDED_WAREHOUSE_TABLES)


def test_the_drift_check_fails_on_a_column_added_without_a_decision():
    dataset = MODEL.dataset("employee_eligibility")
    assert undecided_columns(dataset, [*_physical(dataset), "home_address"]) == {"home_address"}
    assert invented_columns(dataset, [c for c in _physical(dataset) if c != "weight"]) == {"weight"}


def test_the_columns_the_builder_hardcodes_for_currency_exist_in_the_ddl():
    """The live-run subquery and the is_current predicate name physical columns the model does not."""
    tables = warehouse_tables()
    manifest = {"run_id", "run_status", "superseded_by_run_id", "run_completed_at", "run_started_at", "client_id"}
    assert manifest <= set(tables["tcc_ops.run_manifest"])
    for table in ("unit_year_master", "unit_credit_installment"):
        assert "is_current" in tables[f"tcc_gold.{table}"]


def test_the_ddl_parser_reads_columns_alters_and_ignores_comments_and_constraints():
    sql = (
        "CREATE TABLE s.t\n(\n  a INT NOT NULL, -- c, d\n  b DECIMAL(18,2) NULL,\n"
        "  /* e INT, */ CONSTRAINT pk PRIMARY KEY (a, b)\n);\nALTER TABLE s.t ADD f INT NULL;\n"
    )
    assert parse_ddl(sql) == {"s.t": ["a", "b", "f"]}

