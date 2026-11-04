"""The three data tools: what each returns, refuses and records. [CH-16d]

Runs the real capabilities over the shared two-client SQLite database. What is asserted here is the
contract a caller depends on: the catalog is filtered to the caller, a query returns exactly the
rows the source returned and the lane they belong to, every way a question can fail is a typed
refusal with a stable code, and the Copilot Cowork rule for employee-level rows holds.
"""
from __future__ import annotations

import pytest

from application.capabilities import catalog, registry
from application.capabilities.data_catalog import data_catalog
from application.capabilities.data_query import data_distinct_values, data_query
from application.capabilities.errors import DataQueryRefused
from application.capabilities.invoke import CapabilityFailure, invoke
from application.data.exec_errors import QueryBudgetExceeded
from application.data.limits import QueryLimits
from application.data.semantic_model import Source
from application.data_wiring import set_data_query_service
from application.rate_limit import RateLimiter
from tests.data_caps_fixture import CLIENT, MODEL, READER_OID, WRITER_OID, data_service, make_service, person  # noqa: F401

COUNT_BY_METHOD = {"dataset": "unit_month_summary", "client_id": CLIENT, "select": ["method"],
                   "measures": [{"column": "*", "agg": "count", "as": "n"}]}
EMPLOYEE_ROWS = {"dataset": "employee_eligibility", "client_id": CLIENT, "select": ["record_token", "method"], "limit": 3}


def refused(**kwargs) -> DataQueryRefused:
    with pytest.raises(DataQueryRefused) as caught:
        data_query(person(), **kwargs)
    return caught.value


# --------------------------------------------------------------------------- catalog


def test_the_overview_lists_every_dataset_one_line_each(data_service):
    result = data_catalog(person())
    names = [d["name"] for d in result.facts["datasets"]]
    assert "employee_eligibility" in names and "payroll" in names and result.facts["dataset_count"] == len(names)
    assert all("columns" not in d for d in result.facts["datasets"]), "the overview stays compact"
    assert result.provenance.source.startswith("semantic model")


def test_a_dataset_lists_its_columns_without_the_blocked_ones(data_service):
    facts = data_catalog(person(), dataset="employee_period_fact").facts
    columns = {c["name"]: c for c in facts["datasets"][0]["columns"]}
    assert "employee_id" not in columns, "a blocked column is never listed"
    assert columns["record_token"]["sensitivity"] == "employee_level" and columns["hours"]["unit"] == "hours"
    assert columns["hours"]["aggregations"] == sorted(columns["hours"]["aggregations"])
    assert facts["datasets"][0]["engine_notes"], "the catalog says which fixed tool is authoritative"


def test_search_narrows_by_a_word_in_a_name_or_description(data_service):
    facts = data_catalog(person(), search="pay code").facts
    assert 0 < facts["dataset_count"] < len(data_catalog(person()).facts["datasets"])
    assert all("columns" in d for d in facts["datasets"])


def test_the_catalog_holds_no_value_from_the_data(data_service):
    text = str(data_catalog(person(), dataset="employee_eligibility").to_dict())
    assert "-1001-" not in text and "-2002-" not in text, "the fixture's row values never appear in the catalog"


def test_a_dataset_whose_source_is_off_is_left_out_and_counted():
    set_data_query_service(make_service(disabled=(Source.LAKEHOUSE,)))
    try:
        facts = data_catalog(person()).facts
    finally:
        set_data_query_service(None)
    assert "payroll" not in [d["name"] for d in facts["datasets"]]
    assert any("not available in this environment" in n for n in facts["notes"])


def test_cowork_is_told_up_front_that_employee_rows_are_not_available_there(data_service):
    assert any("Cowork" in n for n in data_catalog(person(channel="cowork")).facts["notes"])
    assert not any("Cowork" in n for n in data_catalog(person()).facts["notes"])


# ----------------------------------------------------------------------------- query


def test_an_aggregate_returns_the_rows_exactly_and_travels_in_both_lanes(data_service):
    result = data_query(person(), **COUNT_BY_METHOD)
    assert result.facts["rows"] == [{"method": "min_max", "n": 2}, {"method": "pay_period", "n": 2}]
    assert result.facts["audience"] == "both" and result.user_only_facts == ()
    assert {b.audience for b in result.blocks} == {"both"}
    table = next(b for b in result.blocks if b.kind == "table")
    assert table.rows == (("method", "n"), ("min_max", "2"), ("pay_period", "2"))


def test_the_source_line_the_run_and_the_method_are_stated_in_the_blocks(data_service):
    result = data_query(person(), **COUNT_BY_METHOD)
    text = " ".join(b.text for b in result.blocks)
    assert "Source: warehouse tcc_gold.unit_month_summary" in text and "Min-Max and Pay Period" in text
    assert result.provenance.run_id == f"run-{CLIENT}" and result.provenance.trail_sha256 is None


def test_employee_rows_are_the_persons_lane_only(data_service):
    result = data_query(person(), **EMPLOYEE_ROWS)
    assert result.facts["audience"] == "user" and result.user_only_facts == ("rows",)
    table = next(b for b in result.blocks if b.kind == "table")
    assert table.audience == "user" and any(r[0].startswith("record_token-") for r in table.rows[1:])
    wire = result.to_dict()
    assert wire["user_only_facts"] == ["rows"] and [b.get("audience") for b in wire["blocks"] if b["kind"] == "table"] == ["user"]
    assert "person_level" in str(wire["facts"]["columns"]) and wire["facts"]["row_count"] == 3


def test_a_result_with_no_rows_says_so_and_is_not_an_error(data_service):
    result = data_query(person(), **{**COUNT_BY_METHOD, "filters": [{"column": "worksite_id", "op": "eq", "value": "no-such-site"}]})
    assert result.facts["row_count"] == 0 and result.facts["rows"] == []
    assert not any(b.kind == "table" for b in result.blocks)
    assert any("No rows matched" in b.text for b in result.blocks)


def test_a_capped_result_says_so_in_the_blocks_and_in_the_facts(data_service):
    result = data_query(person(), dataset="unit_year_master", client_id=CLIENT, select=["worksite_id", "tax_year"], limit=2)
    assert result.facts["truncated"] is True and result.facts["row_count"] == 2
    assert any("first 2 rows" in b.text for b in result.blocks if b.kind == "callout")
    assert any("first 2 rows" in w for w in result.warnings), "the narrator is told too"


def test_the_table_shows_at_most_the_display_rows_and_says_it_cut(data_service, monkeypatch):
    from application.capabilities import data_render

    monkeypatch.setattr(data_render, "DISPLAY_ROWS", 2)
    result = data_query(person(), dataset="unit_year_master", client_id=CLIENT, select=["worksite_id", "tax_year"])
    table = next(b for b in result.blocks if b.kind == "table")
    assert len(table.rows) == 1 + 2 and len(result.facts["rows"]) == 4
    assert any("first 2 of 4 rows" in b.text for b in result.blocks if b.kind == "callout")


def test_a_client_other_than_the_one_asked_is_never_in_the_result(data_service):
    text = str(data_query(person(), **COUNT_BY_METHOD).to_dict()) + str(data_query(person(), **EMPLOYEE_ROWS).to_dict())
    assert "-2002-" not in text


# ---------------------------------------------------------------------------- refusals


@pytest.mark.parametrize("spec, code", [
    ({"dataset": "nope", "client_id": CLIENT, "select": ["x"]}, "unknown_dataset"),
    ({"dataset": "unit_month_summary", "client_id": CLIENT, "select": ["nope"]}, "unknown_column"),
    ({"dataset": "employee_period_fact", "client_id": CLIENT, "select": ["employee_id"]}, "blocked_column"),
    ({"dataset": "unit_month_summary", "client_id": CLIENT}, "empty_query"),
    ({"dataset": "unit_month_summary", "select": ["method"]}, "missing_client"),
    ({"dataset": "unit_month_summary", "client_id": CLIENT, "select": ["method"], "limit": 501}, "limit_too_high"),
    ({"dataset": "unit_month_summary", "client_id": CLIENT, "select": ["method"], "sql": "DROP TABLE x"}, "malformed_spec"),
])
def test_every_refusal_has_a_stable_code_and_a_422(data_service, spec, code):
    error = refused(**spec)
    assert error.code == code and error.status == 422 and error.retryable is False


def test_a_refusal_names_the_field_and_never_echoes_the_value(data_service):
    error = refused(dataset="unit_month_summary", client_id=CLIENT, select=["method; DROP TABLE x"])
    assert error.extra.get("field") and "DROP" not in str(error)


def test_a_hostile_filter_value_is_refused_by_name_and_never_reaches_a_statement(data_service):
    error = refused(dataset="unit_month_summary", client_id=CLIENT, select=["worksite_id"],
                    filters=[{"column": "worksite_id", "op": "eq", "value": "x'; DROP TABLE t; --"}])
    assert error.code == "sql_like_value" and error.status == 422 and "DROP" not in str(error)


def test_the_budget_is_a_429_with_the_wait(data_service):
    set_data_query_service(make_service(budget=RateLimiter(1)))
    data_query(person(), **COUNT_BY_METHOD)
    with pytest.raises(DataQueryRefused) as caught:
        data_query(person(), **COUNT_BY_METHOD)
    error = caught.value
    assert (error.code, error.status, error.retryable) == ("query_budget_exceeded", 429, True)
    assert error.extra["retry_after_seconds"] >= 1


def test_the_budget_is_the_persons_not_the_gateways(data_service):
    set_data_query_service(make_service(budget=RateLimiter(1)))
    data_query(person(READER_OID), **COUNT_BY_METHOD)
    data_query(person(WRITER_OID), **COUNT_BY_METHOD)  # a second person, same gateway: not refused


def test_a_source_that_is_off_is_a_503_that_is_not_retryable():
    set_data_query_service(make_service(disabled=(Source.LAKEHOUSE,), limits=QueryLimits()))
    try:
        with pytest.raises(DataQueryRefused) as caught:
            data_query(person(), dataset="payroll", client_id=CLIENT, select=["location_id"])
    finally:
        set_data_query_service(None)
    assert (caught.value.code, caught.value.status, caught.value.retryable) == ("data_source_disabled", 503, False)


# --------------------------------------------------------------------- Copilot Cowork


def test_cowork_is_refused_employee_rows_unless_the_caller_is_a_writer(data_service):
    with pytest.raises(DataQueryRefused) as caught:
        data_query(person(READER_OID, "cowork"), **EMPLOYEE_ROWS)
    assert caught.value.code == "employee_level_not_available" and caught.value.status == 403
    assert "Teams" in str(caught.value) and "individual employees" in str(caught.value)
    assert data_query(person(WRITER_OID, "cowork"), **EMPLOYEE_ROWS).user_only_facts == ("rows",)


def test_cowork_may_ask_an_aggregate_over_employee_data(data_service):
    result = data_query(person(READER_OID, "cowork"), dataset="employee_eligibility", client_id=CLIENT, select=["method"],
                        measures=[{"column": "record_token", "agg": "count_distinct", "as": "people"}])
    assert result.facts["audience"] == "both"


@pytest.mark.parametrize("channel", ["teams", "m365-copilot"])
def test_the_first_party_channels_receive_the_persons_lane(data_service, channel):
    assert data_query(person(READER_OID, channel), **EMPLOYEE_ROWS).facts["audience"] == "user"


def test_a_signed_in_person_calling_the_api_directly_is_not_first_party_and_is_refused_unless_a_writer(data_service):
    """RM-02: a person's own token carries no channel assertion, so it fails closed like Cowork."""
    with pytest.raises(DataQueryRefused) as caught:
        data_query(person(READER_OID, None), **EMPLOYEE_ROWS)
    assert caught.value.code == "employee_level_not_available"
    assert data_query(person(WRITER_OID, None), **EMPLOYEE_ROWS).facts["audience"] == "user"


def test_the_refusal_costs_no_budget_and_reads_nothing(data_service):
    set_data_query_service(make_service(budget=RateLimiter(1)))
    with pytest.raises(DataQueryRefused):
        data_query(person(READER_OID, "cowork"), **EMPLOYEE_ROWS)
    data_query(person(READER_OID, "cowork"), **COUNT_BY_METHOD)  # the one allowed query is still there


# ------------------------------------------------------------------- distinct values


def test_distinct_values_lists_a_dimension_with_row_counts(data_service):
    result = data_distinct_values(person(), CLIENT, "unit_month_summary", "worksite_id")
    values = result.facts["values"]
    assert [v["value"] for v in values] == [f"worksite_id-{CLIENT}-0", f"worksite_id-{CLIENT}-1"]
    assert sum(v["row_count"] for v in values) == 4 and result.facts["value_count"] == 2 and result.facts["truncated"] is False


def test_a_value_is_listed_once_across_the_two_statutory_methods(data_service):
    values = data_distinct_values(person(), CLIENT, "unit_month_summary", "worksite_id").facts["values"]
    assert len({v["value"] for v in values}) == len(values)


def test_distinct_values_is_capped_and_says_so(data_service):
    result = data_distinct_values(person(), CLIENT, "unit_month_summary", "worksite_id", limit=1)
    assert result.facts["truncated"] is True
    assert any("cut at the limit" in b.text for b in result.blocks)


def test_a_limit_counts_values_not_rows_where_both_methods_list_each_value_twice(data_service):
    """The fixture holds two worksites under two methods: four rows. A limit of two must list both worksites."""
    full = data_distinct_values(person(), CLIENT, "unit_month_summary", "worksite_id", limit=2).facts
    assert [v["value"] for v in full["values"]] == [f"worksite_id-{CLIENT}-0", f"worksite_id-{CLIENT}-1"]
    assert full["truncated"] is False and full["value_count"] == 2, "limit=2 rows used to list one worksite and call it cut"
    one = data_distinct_values(person(), CLIENT, "unit_month_summary", "worksite_id", limit=1).facts
    assert one["value_count"] == 1 and one["truncated"] is True and one["values"][0]["row_count"] == 2, "a listed value keeps both readings' rows"


def test_a_dataset_with_no_method_is_fetched_at_the_limit_itself(data_service):
    from application.capabilities.data_query import _rows_to_fetch

    assert _rows_to_fetch("unit_month_summary", 10) == 20 and _rows_to_fetch("employee_period_fact", 10) == 10
    assert _rows_to_fetch("unit_month_summary", 400) == 500, "never past the server's own ceiling"


@pytest.mark.parametrize("dataset, column, code", [
    ("employee_eligibility", "record_token", "column_not_listable"),
    ("employee_period_fact", "hours", "column_not_listable"),
    ("employee_period_fact", "employee_id", "blocked_column"),
    ("unit_month_summary", "nope", "unknown_column"),
    ("nope", "x", "unknown_dataset"),
])
def test_a_column_that_describes_people_or_does_not_exist_is_refused(data_service, dataset, column, code):
    with pytest.raises(DataQueryRefused) as caught:
        data_distinct_values(person(), CLIENT, dataset, column)
    assert caught.value.code == code


# ------------------------------------------------------------- through the invoker


def test_the_invoker_validates_the_schema_and_runs_the_tool(data_service):
    assert invoke("data_query", COUNT_BY_METHOD, person()).tool == "data_query"
    with pytest.raises(CapabilityFailure) as caught:
        invoke("data_query", {**COUNT_BY_METHOD, "extra": 1}, person())
    assert caught.value.code == "invalid_arguments"


def test_a_refusal_leaves_the_invoker_as_the_wire_error_with_its_field(data_service):
    with pytest.raises(CapabilityFailure) as caught:
        invoke("data_query", {**COUNT_BY_METHOD, "select": ["nope"]}, person())
    body = caught.value.body()["error"]
    assert (caught.value.status, body["code"], body["field"]) == (422, "unknown_column", "select")


def test_the_data_tools_are_registered_and_need_the_caller(data_service):
    for name in ("data_catalog", "data_query", "data_distinct_values"):
        assert name in registry.FUNCTIONS and name in registry.NEEDS_PRINCIPAL and catalog.get(name).implemented


# --------------------------------------------------------------- the numeric guard


def _composed(result):
    """The reply the orchestrator composes from a result's own blocks and the facts as they travel (JSON)."""
    from application.composer import compose

    return compose(result.blocks, None, result.to_dict()["facts"])


@pytest.mark.parametrize("dataset", [d.name for d in MODEL.datasets])
def test_every_dataset_renders_through_the_numeric_guard_with_nothing_unvouched(data_service, dataset):
    """Money, headcounts, years, dates, flags and text in every dataset print as the formatter prints them,
    so the guard that checks the finished reply finds every numeral in the facts."""
    columns = [c.logical for c in MODEL.dataset(dataset).columns if c.queryable and c.expression is None and "." not in c.logical][:8]
    result = data_query(person(), dataset=dataset, client_id=CLIENT, select=columns, limit=4)
    composed = _composed(result)
    assert composed.blocks_verified and composed.guard.passed, [v.numeral.text for v in composed.guard.violations]
    assert "Query result" in composed.text


def test_an_aggregate_with_money_and_headcount_renders_exactly(data_service):
    result = data_query(person(), dataset="unit_year_master", client_id=CLIENT, select=["tax_year"], measures=[
        {"column": "annual_credit_usd", "agg": "sum", "as": "credit_usd"}, {"column": "average_headcount", "agg": "avg", "as": "avg_headcount"}])
    composed = _composed(result)
    assert composed.guard.passed and composed.blocks_verified
    table = next(b for b in result.blocks if b.kind == "table")
    assert table.rows[0] == ("method", "tax_year", "credit_usd (USD)", "avg_headcount (headcount)")
    assert table.rows[1][2].startswith("$")


def test_a_text_that_looks_like_a_number_is_shown_verbatim_not_reformatted(data_service):
    from application.capabilities.data_render import cell
    from application.data.plan import ResultColumn
    from application.data.semantic_model import Sensitivity

    column = ResultColumn("code", "dimension", "pay_code", None, Sensitivity.PUBLIC_AGGREGATE)
    assert cell("00123", column) == "00123" and cell(None, column) == "—" and cell(True, column) == "yes"


def test_the_catalog_and_the_distinct_values_render_through_the_guard(data_service):
    for result in (data_catalog(person()), data_catalog(person(), dataset="employee_period_fact"),
                   data_distinct_values(person(), CLIENT, "unit_month_summary", "worksite_id")):
        composed = _composed(result)
        assert composed.blocks_verified and composed.guard.passed, result.tool
