"""The data tools' facts go through the same ledger and guard as every other tool's. [RM-05, CH-06, ADR-008]

`verify_figures` checks a draft against exactly what the conversation was told. For the three data
tools that must hold in both directions:

- what they return IS recorded, so a figure in a data result verifies and the same figure with a digit
  changed does not (there is no data-tool shortcut past the guard);
- what a caller was REFUSED is not: a Cowork caller who may not carry employee rows never has them in
  its conversation, so a figure only those rows held is "not told", never verified by the back door.
"""
from __future__ import annotations

import pytest

from application.capabilities import catalog
from application.capabilities.envelope import Block, ToolResult
from channel.ledger import UNRECORDED_TOOLS
from gateway_harness import OTHER_OID, agent_headers, user_headers, user_token
from test_gw_mcp import call, open_session

VERIFY = "/channel/v1/tools/verify_figures"
DATA_TOOLS = ("data_catalog", "data_query", "data_distinct_values")
SECRET_WAGE = "612.45"

#: tool -> (facts, a figure in them, the same figure with one digit changed). The figures are chosen to be in no other fact.
RESULTS = {
    "data_catalog": ({"dataset_count": 1, "datasets": [{"name": "unit_month_summary", "column_count": 20}]}, "20", "21", {"dataset": "unit_month_summary"}),
    "data_distinct_values": ({"dataset": "unit_month_summary", "column": "worksite_id", "value_count": 7, "values": [], "truncated": False}, "7", "8",
                             {"dataset": "unit_month_summary", "column": "worksite_id", "client_id": 1001}),
    "data_query": ({"dataset": "unit_month_summary", "audience": "both", "row_count": 1, "rows": [{"method": "min_max", "n": 41}]}, "41", "42",
                   {"client_id": 1001, "dataset": "unit_month_summary", "select": ["method"]}),
}


def envelope(tool: str, facts: dict) -> dict:
    return ToolResult(tool=tool, facts=facts, blocks=(Block("heading", text="Result"),)).to_dict()


def verify(gateway, text: str, **headers) -> dict:
    response = gateway.client.post(VERIFY, json={"args": {"draft_text": text}}, headers=agent_headers(**headers))
    assert response.status_code == 200, response.text
    return response.json()["facts"]


@pytest.mark.parametrize("tool", DATA_TOOLS)
def test_a_data_tools_figure_verifies_and_the_same_figure_changed_by_a_digit_does_not(gateway, fake_api, tool):
    facts, figure, changed, args = RESULTS[tool]
    fake_api.replies[tool] = (200, envelope(tool, facts))
    assert gateway.client.post(f"/channel/v1/tools/{tool}", json={"args": args}, headers=agent_headers()).status_code == 200
    assert verify(gateway, f"The result reports {figure}.")["status"] == "pass"
    rejected = verify(gateway, f"The result reports {changed}.")
    assert rejected["status"] == "rejected" and rejected["violations"][0]["token"] == changed


@pytest.mark.parametrize("tool", DATA_TOOLS)
def test_nothing_is_verified_for_a_conversation_the_data_tool_was_never_called_in(gateway, tool):
    _, figure, _, _ = RESULTS[tool]
    assert verify(gateway, f"The result reports {figure}.")["status"] == "rejected"


@pytest.mark.parametrize("tool", DATA_TOOLS)
def test_a_data_tools_facts_are_the_conversations_own(gateway, fake_api, tool):
    facts, figure, _, args = RESULTS[tool]
    fake_api.replies[tool] = (200, envelope(tool, facts))
    gateway.client.post(f"/channel/v1/tools/{tool}", json={"args": args}, headers=agent_headers(conversation="conv-1"))
    assert verify(gateway, f"The result reports {figure}.", conversation="conv-1")["status"] == "pass"
    assert verify(gateway, f"The result reports {figure}.", conversation="conv-2")["status"] == "rejected"


def employee_wages() -> dict:
    facts = {"dataset": "employee_eligibility", "audience": "user", "row_count": 1,
             "rows": [{"record_token": "record_token-1001-7", "total_wages": float(SECRET_WAGE)}]}
    return ToolResult(
        tool="data_query", facts=facts, user_only_facts=("rows",),
        blocks=(Block("heading", text="Query result"), Block("table", rows=(("record_token", "total_wages"), ("record_token-1001-7", SECRET_WAGE)), audience="user")),
    ).to_dict()


EMPLOYEE_ARGS = {"client_id": 1001, "dataset": "employee_eligibility", "select": ["record_token", "total_wages"]}


def test_a_figure_only_the_refused_rows_held_is_not_told_to_the_conversation(gateway, fake_api):
    """A Cowork caller who may not carry employee rows is refused; the rows never reach its conversation, so no
    verification can launder the figure afterwards."""
    fake_api.replies["data_query"] = (200, employee_wages())
    headers = user_headers(user_token(oid=OTHER_OID))
    session, _ = open_session(gateway, headers)
    refused = call(gateway, session, "data_query", EMPLOYEE_ARGS, headers).json()["result"]
    assert refused["isError"] is True and SECRET_WAGE not in str(refused)
    assert not gateway.ledger.facts_for(session)
    checked = call(gateway, session, "verify_figures", {"draft_text": f"Total wages were {SECRET_WAGE}."}, headers).json()["result"]
    assert checked["structuredContent"]["facts"]["status"] == "rejected", "told nothing, so the figure cannot be vouched for"


def test_a_writer_who_was_handed_the_rows_may_verify_a_draft_against_them(gateway, fake_api):
    """The deliberate counterpart: what a person was handed is what their conversation was told."""
    fake_api.replies["data_query"] = (200, employee_wages())
    headers = user_headers()
    session, _ = open_session(gateway, headers)
    assert call(gateway, session, "data_query", EMPLOYEE_ARGS, headers).json()["result"]["isError"] is False
    checked = call(gateway, session, "verify_figures", {"draft_text": f"Total wages were {SECRET_WAGE}."}, headers).json()["result"]
    assert checked["structuredContent"]["facts"]["status"] == "pass"


# ---------------------------------------------------------------------- structure


def test_no_data_tool_is_among_the_results_the_ledger_forgets():
    assert not set(DATA_TOOLS) & UNRECORDED_TOOLS


def _known_tools() -> dict:
    """Every tool a caller can name: the catalog's, and the gateway's own plumbing tool."""
    from channel.tools import PING_SPEC

    return {spec.name: spec for spec in (*catalog.CATALOG, PING_SPEC)}


def test_every_tool_the_ledger_forgets_is_a_tool_that_exists():
    """A stale name here is a silent door: a renamed tool would be recorded again, or a new one never."""
    assert UNRECORDED_TOOLS <= set(_known_tools())


def test_the_ledger_forgets_only_what_has_no_figure_to_verify():
    """Positions and counts of the check itself, a ticket, a link: not the engine's figures. Never a read of data."""
    specs = _known_tools()
    for name in UNRECORDED_TOOLS:
        assert catalog.LOOKUP not in specs[name].tags and not name.startswith("data_")
