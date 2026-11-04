"""The data-query service: limits, refusals and provenance on every result. [CH-16c]

Runs the real builder and model over SQLite (the shared two-client fixture) and over a scripted
executor where a scenario cannot be produced by data: a timeout, a slow query holding a slot.
"""
from __future__ import annotations

import json
import threading

import pytest

from application.data.exec_errors import (
    DataSourceDisabled, DataSourceUnavailable, QueryBudgetExceeded, QueryBusy, QueryTimeout,
)
from application.data.executor import Rows
from application.data.limits import Bulkhead, QueryLimits
from application.data.semantic_model import Source, default_model
from application.data.service import DataQueryService
from application.data.spec import QuerySpec
from application.data.dialect import Dialect
from application.rate_limit import RateLimiter
from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
from tests.data_fixture import CLIENT_A, CLIENT_B, ROWS_PER_CLIENT, build_database

MODEL = default_model()
LOOKUP_COLUMNS = ("run_id", "rule_pack_version", "step1_assumption_set_id", "onezero_assumption_set_id",
                  "run_completed_at", "run_started_at", "superseded_by_run_id")


def spec(**overrides):
    base = {"dataset": "unit_month_summary", "client_id": CLIENT_A, "select": ["method"],
            "measures": [{"column": "*", "agg": "count"}], "group_by": ["method"]}
    return QuerySpec.from_dict({**base, **overrides})


@pytest.fixture()
def database():
    return build_database(MODEL)


def sqlite_service(database, **kwargs):
    executor = SqliteDataQueryExecutor(lambda: database)
    return DataQueryService(MODEL, {Source.WAREHOUSE: executor, Source.LAKEHOUSE: executor}, **kwargs)


class ScriptedExecutor:
    dialect = Dialect.SQLITE

    def __init__(self, *, rows=None, error=None, gate=None):
        self.calls, self.rows, self.error, self.gate = [], rows, error, gate

    def execute(self, sql, params, *, client_id, timeout_s, max_rows):
        self.calls.append({"sql": sql, "client_id": client_id, "timeout_s": timeout_s, "max_rows": max_rows})
        if self.gate:
            self.gate.wait(5)
        if self.error:
            raise self.error
        if "run_manifest" in sql:
            return Rows(LOOKUP_COLUMNS, (("run-1", "pack", "s1", "oz", "2023-02-01", "2023-01-31", None),))
        return self.rows or Rows(("method", "row_count"), (("min_max", 1),))


def scripted_service(executor, **kwargs):
    return DataQueryService(MODEL, {Source.WAREHOUSE: executor}, **kwargs)


# ------------------------------------------------------------------ results and lanes


def test_a_grouped_query_returns_rows_for_the_asking_client_only(database):
    result = sqlite_service(database).run(spec(), principal="u1")
    assert dict(result.rows) == {"min_max": 2, "pay_period": 2}
    assert result.audience == "both" and result.employee_level_labels == ()
    assert [c.label for c in result.columns] == ["method", "row_count"]
    other = sqlite_service(database).run(spec(client_id=CLIENT_B), principal="u1")
    assert other.provenance.client_id == CLIENT_B and other.provenance.run.run_id == f"run-{CLIENT_B}"


def test_employee_level_rows_are_in_the_user_lane(database):
    result = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "employee_eligibility", "client_id": CLIENT_A, "select": ["record_token", "method"],
                             "limit": 3}), principal="u1")
    assert result.audience == "user" and "record_token" in result.employee_level_labels


# ------------------------------------------------------------------ the row cap


def test_the_spec_limit_truncates_and_says_so(database):
    result = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id", "tax_year"], "limit": 2}),
        principal="u1")
    assert len(result.rows) == 2 and result.truncated is True
    assert result.provenance.row_count == 2 and result.provenance.row_limit == 2
    assert any("first 2 rows" in n for n in result.provenance.notes)


def test_a_result_that_fits_is_not_truncated(database):
    result = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id", "tax_year"],
                             "limit": 100}), principal="u1")
    assert result.truncated is False and len(result.rows) == ROWS_PER_CLIENT
    assert not any("first" in n for n in result.provenance.notes)


def test_the_server_cap_lowers_the_limit_and_the_note_says_so():
    executor = ScriptedExecutor()
    service = scripted_service(executor, limits=QueryLimits(hard_max_rows=50))
    result = service.run(spec(limit=200), principal="u1")
    assert executor.calls[0]["max_rows"] == 50 and result.provenance.row_limit == 50
    assert any("row cap (50)" in n for n in result.provenance.notes)


def test_the_limits_cannot_exceed_the_specification_cap():
    with pytest.raises(ValueError):
        QueryLimits(hard_max_rows=501)
    with pytest.raises(ValueError):
        QueryLimits(timeout_s=0)
    with pytest.raises(ValueError):
        QueryLimits(max_concurrency=0)


# ------------------------------------------------------------------ the timeout


def test_the_timeout_is_passed_to_the_executor_and_a_timeout_returns_nothing():
    executor = ScriptedExecutor()
    scripted_service(executor, limits=QueryLimits(timeout_s=7)).run(spec(), principal="u1")
    assert executor.calls[0]["timeout_s"] == 7
    timed_out = ScriptedExecutor(error=QueryTimeout("too slow"))
    with pytest.raises(QueryTimeout) as caught:
        scripted_service(timed_out).run(spec(), principal="u1")
    assert caught.value.code == "query_timeout"


def test_a_lookup_that_times_out_also_fails_the_whole_query():
    class FailsOnLookup(ScriptedExecutor):
        def execute(self, sql, params, **kw):
            if "run_manifest" in sql:
                raise QueryTimeout("slow")
            return super().execute(sql, params, **kw)

    with pytest.raises(QueryTimeout):
        scripted_service(FailsOnLookup()).run(spec(), principal="u1")


# ------------------------------------------------------------------ budget and bulkhead


def test_a_person_over_budget_is_refused_not_queued():
    executor = ScriptedExecutor()
    service = scripted_service(executor, budget=RateLimiter(2))
    service.run(spec(), principal="u1")
    service.run(spec(), principal="u1")
    calls = len(executor.calls)
    with pytest.raises(QueryBudgetExceeded) as caught:
        service.run(spec(), principal="u1")
    assert caught.value.code == "query_budget_exceeded" and caught.value.retry_after_s >= 1
    assert len(executor.calls) == calls
    service.run(spec(), principal="u2")


def test_a_specification_that_may_not_run_costs_no_budget():
    executor = ScriptedExecutor()
    service = scripted_service(executor, budget=RateLimiter(1))
    with pytest.raises(Exception):
        service.run(spec(select=["no_such_column"]), principal="u1")
    service.run(spec(), principal="u1")
    assert len(executor.calls) >= 1


def test_the_bulkhead_refuses_beyond_its_slots():
    bulkhead = Bulkhead(2, wait_s=0.01)
    with bulkhead.slot(), bulkhead.slot():
        with pytest.raises(QueryBusy) as caught:
            with bulkhead.slot():
                pass
        assert caught.value.code == "query_busy"
    with bulkhead.slot():
        pass


def test_concurrent_queries_beyond_the_bulkhead_are_refused():
    gate = threading.Event()
    executor = ScriptedExecutor(gate=gate)
    service = scripted_service(executor, limits=QueryLimits(max_concurrency=1, busy_wait_s=0.01))
    first = threading.Thread(target=lambda: service.run(spec(), principal="u1"))
    first.start()
    while not executor.calls:
        pass
    try:
        with pytest.raises(QueryBusy):
            service.run(spec(), principal="u2")
    finally:
        gate.set()
        first.join(5)
    service.run(spec(), principal="u2")


# ------------------------------------------------------------------ sources


def test_a_disabled_source_is_refused_and_a_missing_one_is_unavailable(database):
    executor = SqliteDataQueryExecutor(lambda: database)
    source = QuerySpec.from_dict({"dataset": "payroll", "client_id": CLIENT_A, "measures": [{"column": "*", "agg": "count"}]})
    off = DataQueryService(MODEL, {Source.WAREHOUSE: executor, Source.LAKEHOUSE: executor}, disabled=[Source.LAKEHOUSE])
    with pytest.raises(DataSourceDisabled) as caught:
        off.run(source, principal="u1")
    assert caught.value.code == "data_source_disabled" and Source.LAKEHOUSE not in off.available_sources()
    with pytest.raises(DataSourceUnavailable):
        DataQueryService(MODEL, {Source.WAREHOUSE: executor}).run(source, principal="u1")
    on = DataQueryService(MODEL, {Source.WAREHOUSE: executor, Source.LAKEHOUSE: executor})
    assert on.run(source, principal="u1").provenance.source_line == "Source: lakehouse tcc_source.Payroll"


def test_an_unknown_dataset_is_the_typed_validation_error(database):
    with pytest.raises(Exception) as caught:
        sqlite_service(database).run(spec(dataset="nope"), principal="u1")
    assert caught.value.code == "unknown_dataset"


def test_known_years_come_from_the_callback(database):
    service = sqlite_service(database, years_for=lambda client: {2023})
    service.run(spec(tax_years=[2023]), principal="u1")
    with pytest.raises(Exception) as caught:
        service.run(spec(tax_years=[2019]), principal="u1")
    assert caught.value.code == "tax_year_out_of_range"


# ------------------------------------------------------------------ provenance


def test_provenance_names_the_source_the_run_and_the_method(database):
    p = sqlite_service(database).run(spec(), principal="u1").provenance
    assert p.source_line == "Source: warehouse tcc_gold.unit_month_summary"
    assert p.dataset == "unit_month_summary" and p.physical_table == "tcc_gold.unit_month_summary"
    assert p.method == "both" and p.method_dependent is True
    assert p.run.run_id == f"run-{CLIENT_A}" and p.run.rule_pack_version and p.run.onezero_assumption_set_id
    assert p.as_of_basis == "run_completed_at" and p.as_of == p.run.completed_at
    assert any("both Min-Max and Pay Period" in n for n in p.notes)


def test_a_named_method_is_carried_explicitly(database):
    p = sqlite_service(database).run(spec(method="pay_period"), principal="u1").provenance
    assert p.method == "pay_period" and any("pay_period only" in n for n in p.notes)


def test_a_method_dependent_dataset_never_silently_picks_one(database):
    result = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "run_method_summary", "client_id": CLIENT_A, "select": ["tax_year"]}), principal="u1")
    assert result.provenance.method == "both" and "method" in [c.label for c in result.columns]


def test_a_dataset_without_a_run_reports_query_time(database):
    result = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "run_manifest", "client_id": CLIENT_A, "select": ["run_id"]}), principal="u1")
    p = result.provenance
    assert p.run is None and p.as_of_basis == "query_time" and p.currency == "none"
    current = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id"]}), principal="u1")
    assert current.provenance.run is None and any("Current rows only" in n for n in current.provenance.notes)


def test_the_hash_covers_structure_not_values(database):
    service = sqlite_service(database)
    one = service.run(spec(filters=[{"column": "worksite_id", "op": "eq", "value": "alpha"}]), principal="u1").provenance
    two = service.run(spec(filters=[{"column": "worksite_id", "op": "eq", "value": "beta"}]), principal="u1").provenance
    assert one.statement_sha256 == two.statement_sha256 and one.params_sha256 == two.params_sha256
    assert len(one.statement_sha256) == 64 and one.param_count == two.param_count
    different = service.run(spec(select=["method", "tax_year"], group_by=["method", "tax_year"]), principal="u1").provenance
    assert different.statement_sha256 != one.statement_sha256


def test_no_filter_value_leaks_through_the_hash_and_a_sensitive_one_is_redacted(database):
    token = "tok-" + "a1b2c3" * 4
    p = sqlite_service(database).run(
        QuerySpec.from_dict({"dataset": "employee_eligibility", "client_id": CLIENT_A, "select": ["method"],
                             "filters": [{"column": "record_token", "op": "eq", "value": token}]}), principal="u1").provenance
    text = json.dumps(p.to_dict())
    assert token not in text
    assert p.filters == ({"column": "record_token", "op": "eq", "value": "<redacted>"},)


def test_a_public_filter_value_is_shown_and_the_provenance_is_json_safe(database):
    p = sqlite_service(database).run(spec(filters=[{"column": "tax_year", "op": "between", "value": [2022, 2023]}]),
                                     principal="u1").provenance
    assert p.filters == ({"column": "tax_year", "op": "between", "value": [2022, 2023]},)
    data = json.loads(json.dumps(p.to_dict()))
    assert data["group_by"] == ["method"] and data["measures"][0]["agg"] == "count"
    assert data["statement_sha256"] and "client_id = " not in json.dumps(data)


def test_the_parameter_structure_is_types_in_order(database):
    from application.data.provenance import param_structure

    assert param_structure([7, "x", 1.5, None]) == ["int", "str", "float", "NoneType"]
