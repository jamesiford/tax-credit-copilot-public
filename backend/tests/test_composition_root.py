"""The ports the composition root binds, behave as the adapters they replaced did. [RM-17]

The use cases once imported `infrastructure` directly. These tests pin that going through a
port changed no behaviour: the same classes are raised and stored, and an adapter function
replaced after start-up is the one a use case calls.
"""
from __future__ import annotations

import bootstrap.wiring  # noqa: F401 - binds the ports under test
from application import gold_ports, source_ports


def test_a_use_case_reads_pay_periods_through_whatever_the_adapter_function_is_now(monkeypatch):
    from infrastructure.payroll import pay_period_source

    seen = []
    monkeypatch.setattr(pay_period_source, "load_pay_periods", lambda account_id=None: seen.append(account_id) or ["row"])

    assert source_ports.load_pay_periods(7) == ["row"]
    assert seen == [7]


def test_the_fiscal_window_port_returns_what_the_adapter_returns(monkeypatch):
    from infrastructure.payroll import fiscal_source

    monkeypatch.setattr(fiscal_source, "window_for_state_year", lambda account_id, state, year: ("begin", "end"))

    assert source_ports.window_for_state_year(1, "GA", 2023) == ("begin", "end")


def test_the_source_reader_factory_builds_the_adapter_each_call():
    from infrastructure.persistence.source_sql import SourceSqlReader

    first, second = source_ports.new_source_reader(), source_ports.new_source_reader()

    assert isinstance(first, SourceSqlReader) and first is not second


def test_the_section_9_count_is_the_stores_own_number_of_invariants():
    from infrastructure.persistence.warehouse_gold import SECTION_9_QUERIES

    assert gold_ports.section_9_query_count() == len(SECTION_9_QUERIES) > 0


def test_the_adapter_raises_the_applications_own_error():
    from infrastructure.persistence.warehouse_gold import GoldWriteFailed

    assert GoldWriteFailed is gold_ports.GoldWriteFailed


def test_the_finding_record_is_one_class_whether_a_use_case_or_a_store_names_it():
    from domain.findings import FindingResolution
    from infrastructure.persistence.sqlite_findings import FindingResolution as stored

    assert stored is FindingResolution


def test_the_run_manifest_columns_are_one_tuple_for_the_use_case_and_the_adapter():
    from domain.warehouse import RUN_MANIFEST_COLUMNS
    from infrastructure.persistence import fabric_warehouse

    assert fabric_warehouse._MANIFEST_COLUMNS is RUN_MANIFEST_COLUMNS
