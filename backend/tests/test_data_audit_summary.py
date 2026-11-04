"""What a data call's audit line says, and what it must never say. [CH-16d]

A timeline reader sees which dataset was grouped by what, with which measures and which filters, and
the limit. A value is shown only for a public dimension; anything the model supplied that is not a
plain identifier is replaced, so a hostile string cannot reach a timeline through a column name.
"""
from __future__ import annotations

from application.channel_audit import SENSITIVE_KEY, AuditCall, summarise_request
from application.data.audit_summary import REDACTED, summarise_data_call

QUERY = {
    "dataset": "employee_eligibility", "client_id": 1001, "select": ["method", "worksite_id"], "group_by": ["method"],
    "measures": [{"column": "record_token", "agg": "count_distinct", "as": "people"}, {"column": "*", "agg": "count"}],
    "filters": [{"column": "worksite_id", "op": "in", "value": ["GA-001", "GA-002"]},
                {"column": "record_token", "op": "eq", "value": "SECRET-TOKEN"},
                {"column": "nope", "op": "eq", "value": "SECRET-UNKNOWN"}],
    "tax_years": [2022, 2023], "method": "min_max", "limit": 25,
}


def test_the_line_names_dataset_dimensions_measures_filters_years_and_limit():
    summary = summarise_data_call("data_query", QUERY)
    assert summary["dataset"] == "employee_eligibility" and summary["select"] == "method,worksite_id"
    assert summary["measures"] == "count_distinct(record_token), count(*)" and summary["group_by"] == "method"
    assert summary["years"] == "2022|2023" and summary["method"] == "min_max" and summary["limit"] == "25"


def test_a_filter_value_is_shown_only_for_a_public_dimension():
    public = {"dataset": "unit_month_summary", "filters": [{"column": "worksite_id", "op": "in", "value": ["GA-001", "GA-002"]}]}
    assert "worksite_id in GA-001|GA-002" in summarise_data_call("data_query", public)["filters"]
    filters = summarise_data_call("data_query", QUERY)["filters"]
    assert f"record_token eq {REDACTED}" in filters and f"nope eq {REDACTED}" in filters
    assert "SECRET" not in filters


def test_a_range_of_years_is_summarised_as_a_range():
    assert summarise_data_call("data_query", {**QUERY, "tax_years": {"from": 2020, "to": 2023}})["years"] == "2020-2023"


def test_a_name_that_is_not_a_plain_identifier_never_reaches_the_line():
    hostile = {"dataset": "x'; DROP TABLE y;--", "select": ["a b", "c\nd"], "filters": [{"column": "x\ty", "op": "eq; --", "value": 1}]}
    text = str(summarise_data_call("data_query", hostile))
    assert "DROP" not in text and "<invalid>" in text and "\n" not in text.replace("\\n", "")


def test_a_malformed_call_is_summarised_not_raised():
    for bad in ({"filters": "x"}, {"measures": [1, None]}, {"select": "x", "tax_years": "y"}, {"filters": [None]}, {}):
        assert isinstance(summarise_data_call("data_query", bad), dict)


def test_distinct_values_names_the_column_and_other_tools_are_left_to_the_default_summary():
    assert summarise_data_call("data_distinct_values", {"dataset": "payroll", "column": "pay_code", "client_id": 1})["column"] == "pay_code"
    assert summarise_data_call("client_trend", {"client_id": 1}) is None and summarise_data_call("data_catalog", {}) is None


def test_the_audit_summary_replaces_the_arguments_in_the_human_line_only():
    summary = summarise_data_call("data_query", QUERY)
    line = summarise_request(summary)
    assert "dataset=employee_eligibility" in line and "SECRET" not in line
    call = AuditCall(tool_name="data_query", action_kind="read", args=QUERY, summary=summary)
    assert call.summary is summary and call.args is QUERY, "the hash is still over the whole request"


def test_no_summary_key_is_one_the_auditor_drops_as_sensitive():
    assert not [k for k in summarise_data_call("data_query", QUERY) if SENSITIVE_KEY.search(k)]
