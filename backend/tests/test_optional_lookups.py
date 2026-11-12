"""A source without the lookup tables the customer does not supply still loads. [03.5]

`for_account` used to read every table in `TABLE_SPECS` eagerly, so a lakehouse without
`PayFrequency` and `EntityFiscalYearRules` could not load a single client. The two are lookups the
headcount does not need (the fiscal rules decide a WINDOW, which keeps its flagged calendar-year
fallback), so an absent table is read as "no rows", logged once, and recorded on the dataset.
An outage is a different fact: a table that exists but cannot be read still raises.
"""
from __future__ import annotations

import logging

import pytest
from local_lakehouse import use_local_lakehouse, write_lakehouse

from data.source import from_fabric
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from data.source.to_bcs import source_to_bcs_rows


@pytest.fixture(scope="module")
def dataset():
    return build_synthetic_dataset(SYNTHETIC_CLIENTS[0])


@pytest.fixture
def reader(tmp_path, monkeypatch, request, dataset):
    write_lakehouse(tmp_path, dataset, skip=getattr(request, "param", ()))
    use_local_lakehouse(monkeypatch, tmp_path)
    monkeypatch.setattr(from_fabric, "_WARNED_MISSING", set())
    yield from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="dbo")
    from_fabric.clear_cache()


def test_control_every_table_present_loads(reader, dataset):
    loaded = reader.for_account(dataset.account.account_id)
    assert loaded is not None and loaded.missing_tables == ()
    assert len(loaded.payroll) == len(dataset.payroll) and loaded.fiscal_year_rules


@pytest.mark.parametrize("reader", [("PayFrequency", "EntityFiscalYearRules")], indirect=True)
def test_a_source_without_the_two_unsupplied_lookups_still_loads(reader, dataset, caplog):
    with caplog.at_level(logging.WARNING):
        loaded = reader.for_account(dataset.account.account_id)
    assert loaded is not None
    assert loaded.pay_frequencies == [] and loaded.fiscal_year_rules == []
    assert set(loaded.missing_tables) == {"PayFrequency", "EntityFiscalYearRules"}
    assert "EntityFiscalYearRules" in caplog.text and "absent" in caplog.text
    assert len(loaded.payroll) == len(dataset.payroll), "every payroll row still arrives"
    assert source_to_bcs_rows(loaded), "the engine's projection still works"


@pytest.mark.parametrize("reader", [("PayFrequency", "EntityFiscalYearRules")], indirect=True)
def test_the_absence_is_logged_once_per_table(reader, dataset, caplog):
    with caplog.at_level(logging.WARNING):
        reader.for_account(dataset.account.account_id)
        from_fabric.clear_cache()
        reader.for_account(dataset.account.account_id)
    assert caplog.text.count("source table EntityFiscalYearRules") == 1


@pytest.mark.parametrize("reader", [("EntityFiscalYearRules",)], indirect=True)
def test_missing_fiscal_rules_keep_the_flagged_calendar_year(reader, dataset, monkeypatch):
    """The window is statute-affecting, so it must not be silently invented: it stays `assumed`."""
    from infrastructure.payroll import fiscal_source

    monkeypatch.setattr("tools.fabric_source.active_data_source", lambda: "lakehouse")
    monkeypatch.setattr("infrastructure.persistence.source_sql.SourceSqlReader.is_configured", lambda self: False)
    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "for_account", lambda self, account_id: reader.for_account(account_id))
    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "is_configured", lambda self: True)

    window = fiscal_source.client_fiscal_window(dataset.account.account_id, 2023, "begins")
    assert window.basis == "assumed_calendar"
    assert "calendar year is assumed" in window.note


@pytest.mark.parametrize("reader", [("PayCode",)], indirect=True)
def test_a_missing_pay_code_table_is_not_optional(reader, dataset):
    """Pay-code names decide which pay is counted, so the engine cannot run without them."""
    from deltalake.exceptions import TableNotFoundError

    with pytest.raises(TableNotFoundError):
        reader.for_account(dataset.account.account_id)


def test_a_table_that_exists_but_cannot_be_read_still_raises(reader, dataset, monkeypatch):
    original = from_fabric.FabricLakehouseReader._read

    def flaky(self, table, options, account_id):
        if table == "PayFrequency":
            raise OSError("connection timed out")
        return original(self, table, options, account_id)

    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "_read", flaky)
    with pytest.raises(OSError, match="timed out"):
        reader.for_account(dataset.account.account_id)
