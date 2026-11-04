"""Data results at the gateway: the Copilot Cowork rule, the audit line and the tool list. [CH-16d]

The API refuses to run an employee-level query for a Cowork caller who is not a writer. These tests
cover the second check, on what comes BACK: whatever the API forwards, a Cowork caller who may not
carry employee rows is never handed them, and the refusal is audited as one. They also pin what a
data call's audit line says and leaves out, and that the three tools are offered read-only.
"""
from __future__ import annotations

from application.capabilities import catalog
from application.capabilities.envelope import Block, Provenance, ToolResult
from gateway_harness import OTHER_OID, USER_OID, agent_headers, user_headers, user_token
from test_gw_mcp import MCP, call, open_session, rpc

SECRET_TOKEN = "record_token-1001-7"


def employee_rows() -> dict:
    """What the API returns for an employee-level query: the rows in the person's lane."""
    facts = {"dataset": "employee_eligibility", "audience": "user", "row_count": 1, "rows": [{"record_token": SECRET_TOKEN}]}
    return ToolResult(
        tool="data_query", facts=facts, user_only_facts=("rows",), provenance=Provenance(run_id="run-1", source="Source: warehouse tcc_gold.x"),
        blocks=(Block("heading", text="Query result"), Block("table", rows=(("record_token",), (SECRET_TOKEN,)), audience="user")),
    ).to_dict()


def aggregate() -> dict:
    facts = {"dataset": "unit_month_summary", "audience": "both", "row_count": 1, "rows": [{"method": "min_max", "n": 2}]}
    return ToolResult(tool="data_query", facts=facts, blocks=(Block("table", rows=(("method", "n"), ("min_max", "2"))),)).to_dict()


ARGS = {"client_id": 1001, "dataset": "employee_eligibility", "select": ["record_token"]}
COWORK_NON_WRITER = user_headers(user_token(oid=OTHER_OID))


def mcp_call(gateway, headers, arguments=ARGS):
    session, _ = open_session(gateway, headers)
    return call(gateway, session, "data_query", arguments, headers).json()["result"]


def test_cowork_is_not_handed_employee_rows_unless_the_caller_is_a_writer(gateway, fake_api):
    fake_api.replies["data_query"] = (200, employee_rows())
    result = mcp_call(gateway, COWORK_NON_WRITER)
    assert result["isError"] is True and "individual employees" in result["content"][0]["text"]
    assert SECRET_TOKEN not in str(result), "not in the text, not in structuredContent"
    assert result["structuredContent"]["error"]["code"] == "employee_level_not_available"


def test_the_refusal_is_audited_as_a_refusal_and_the_rows_never_enter_the_ledger(gateway, fake_api):
    fake_api.replies["data_query"] = (200, employee_rows())
    session, _ = open_session(gateway, COWORK_NON_WRITER)
    call(gateway, session, "data_query", ARGS, COWORK_NON_WRITER)
    ended = [e for e in gateway.events(OTHER_OID) if e.phase == "end"]
    assert [e.outcome for e in ended] == ["refused"] and "employee_level_not_available" in ended[0].error
    assert not gateway.ledger.facts_for(session)


def test_a_cowork_writer_receives_the_rows(gateway, fake_api):
    fake_api.replies["data_query"] = (200, employee_rows())
    result = mcp_call(gateway, user_headers())
    assert result["isError"] is False and SECRET_TOKEN in result["content"][0]["text"]


def test_an_aggregate_goes_to_a_cowork_caller_who_is_not_a_writer(gateway, fake_api):
    fake_api.replies["data_query"] = (200, aggregate())
    result = mcp_call(gateway, COWORK_NON_WRITER, {"client_id": 1001, "dataset": "unit_month_summary", "select": ["method"]})
    assert result["isError"] is False and "min_max" in result["content"][0]["text"]


def test_teams_receives_the_persons_lane_for_the_orchestrator_to_render(gateway, fake_api):
    fake_api.replies["data_query"] = (200, employee_rows())
    response = gateway.client.post("/channel/v1/tools/data_query", json={"args": ARGS}, headers=agent_headers(oid=OTHER_OID))
    assert response.status_code == 200 and response.json()["user_only_facts"] == ["rows"]


def test_an_unknown_audience_word_is_read_as_the_persons_lane_in_the_text(gateway, fake_api):
    odd = aggregate()
    odd["blocks"][0]["audience"] = "everyone"
    fake_api.replies["data_query"] = (200, odd)
    result = mcp_call(gateway, COWORK_NON_WRITER, {"client_id": 1001, "dataset": "unit_month_summary", "select": ["method"]})
    assert result["isError"] is True, "a word the gateway does not know is treated as `user`, never `both`"


def test_the_audit_line_names_columns_and_operators_and_values_only_where_public(gateway, fake_api):
    fake_api.replies["data_query"] = (200, aggregate())
    args = {"client_id": 1001, "dataset": "employee_eligibility", "select": ["method"], "limit": 25,
            "measures": [{"column": "record_token", "agg": "count_distinct", "as": "people"}],
            "filters": [{"column": "record_token", "op": "eq", "value": SECRET_TOKEN},
                        {"column": "method", "op": "eq", "value": "min_max"}]}
    mcp_call(gateway, user_headers(), args)
    begin = next(e for e in gateway.events() if e.phase == "begin" and e.tool_name == "data_query")
    summary = begin.request_summary
    assert "dataset=employee_eligibility" in summary and "select=method" in summary and "limit=25" in summary
    assert "count_distinct(record_token)" in summary and "record_token eq <redacted>" in summary
    assert "method eq min_max" in summary and SECRET_TOKEN not in summary
    assert begin.is_deterministic_path is True and begin.client_id == 1001


def test_the_run_id_is_recorded_when_the_result_carries_one(gateway, fake_api):
    fake_api.replies["data_query"] = (200, employee_rows())
    mcp_call(gateway, user_headers())
    end = next(e for e in gateway.events() if e.phase == "end" and e.tool_name == "data_query")
    assert end.run_id == "run-1" and end.outcome == "ok"


def test_the_three_tools_are_offered_read_only_and_idempotent(gateway):
    session, _ = open_session(gateway)
    tools = {t["name"]: t for t in gateway.client.post(
        MCP, json=rpc("tools/list"), headers={**user_headers(), "Mcp-Session-Id": session}).json()["result"]["tools"]}
    for name in ("data_catalog", "data_query", "data_distinct_values"):
        hints = tools[name]["annotations"]
        assert (hints["readOnlyHint"], hints["idempotentHint"], hints["destructiveHint"], hints["openWorldHint"]) == (True, True, False, False)
        assert tools[name]["inputSchema"] == catalog.get(name).schema
    assert "does not interpret" in tools["data_query"]["description"] and "authoritative" in tools["data_query"]["description"]
