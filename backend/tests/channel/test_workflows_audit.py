"""One person's trail is theirs alone, and every surface says the same thing. [CH-11]

Two people use the gateway at once, one through Cowork and one through the orchestrator, and
what each did must be readable on its own: through the audit endpoint and through the
operator's script, with the channel and the strength of the identity recorded right. And
the same read, asked four ways (the gateway over REST, over MCP, the API's capability
endpoint, the portal's own endpoint), must give the same figures and the same words.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from application.capabilities import registry
from channel.render import render_tool_text
from tests.test_agent_principal import acting_header, mint_app
from tests.test_auth import mint
from workflow_harness import (  # noqa: F401 - fixtures
    OTHER_OID, PAYROLL_CLIENT, USER_OID, McpSurface, RestSurface, entra, flow, gold, service, world,
)

REPO = Path(__file__).resolve().parents[3]
ENGAGE = {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope", "note": "signed"}


def api() -> TestClient:
    import main

    return TestClient(main.app)


def operator_headers() -> dict[str, str]:
    """A signed-in operator with the human role: the audit endpoint refuses a service."""
    return {"Authorization": f"Bearer {mint()}"}


def channel_audit_script():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("channel_audit_script", REPO / "scripts" / "channel-audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------- audit separation


@pytest.fixture
def interleaved(flow):
    """The writer through Cowork and a reader through Teams, calls alternating, one change by the writer."""
    cowork, teams = McpSurface(flow.gw, USER_OID), RestSurface(flow.gw, OTHER_OID, "conv-other")
    cowork.call("book_rank")
    teams.call("client_trend", {"client_id": 2002})
    prepared = cowork.call("engagement_set_prepare", ENGAGE)
    teams.call("book_rank")
    teams.call("engagement_set_prepare", ENGAGE)           # refused: not a writer
    committed = cowork.commit("engagement_set", ENGAGE, prepared.token, "cowork-1")
    teams.call("client_situation", {"client_id": 2003})
    cowork.call("client_trend", {"client_id": 2001})
    assert committed.ok
    return cowork, teams, prepared


def test_each_persons_events_are_only_theirs_through_the_endpoint(flow, interleaved):
    http = api()
    mine = http.get("/api/audit/channel", params={"user_oid": USER_OID}, headers=operator_headers()).json()["events"]
    theirs = http.get("/api/audit/channel", params={"user_oid": OTHER_OID}, headers=operator_headers()).json()["events"]
    assert {e["user_oid"] for e in mine} == {USER_OID} and {e["user_oid"] for e in theirs} == {OTHER_OID}
    assert {e["tool_name"] for e in mine} == {"book_rank", "engagement_set_prepare", "engagement_set_commit", "client_trend"}
    assert {e["tool_name"] for e in theirs} == {"client_trend", "book_rank", "engagement_set_prepare", "client_situation"}
    assert not {e["audit_id"] for e in mine} & {e["audit_id"] for e in theirs}


def test_channel_and_identity_assurance_are_recorded_for_what_each_person_used(flow, interleaved):
    mine, theirs = flow.events(USER_OID), flow.events(OTHER_OID)
    assert {(e.channel, e.identity_assurance) for e in mine} == {("cowork", "delegated")}
    assert {(e.channel, e.identity_assurance) for e in theirs} == {("teams", "channel-asserted")}
    assert {e.conversation_id for e in theirs} == {"conv-other"} and len({e.conversation_id for e in mine}) == 1


def test_a_commit_points_at_the_preview_it_confirmed_and_a_refusal_is_recorded_as_one(flow, interleaved):
    _, _, prepared = interleaved
    mine = flow.events(USER_OID)
    refs = {e.tool_name: e.confirmation_ref for e in mine if e.phase == "end" and e.tool_name.startswith("engagement_set")}
    assert refs == {"engagement_set_prepare": prepared.confirmation_id, "engagement_set_commit": prepared.confirmation_id}
    refused = [e for e in flow.events(OTHER_OID) if e.tool_name == "engagement_set_prepare" and e.phase in ("end", "single")]
    assert [e.outcome for e in refused] == ["refused"]
    assert not [e for e in flow.events(OTHER_OID) if e.tool_name.endswith("_commit")]


def test_the_operators_script_shows_one_person_and_only_that_person(flow, interleaved, capsys):
    script = channel_audit_script()
    assert script.main(["--user", USER_OID], repository=flow.world.audit, writers=flow.world.writers) == 0
    mine = capsys.readouterr().out
    assert script.main(["--user", OTHER_OID], repository=flow.world.audit, writers=flow.world.writers) == 0
    theirs = capsys.readouterr().out
    assert "engagement_set_commit" in mine and "engagement_set_commit" not in theirs
    assert "client_situation" in theirs and "client_situation" not in mine
    assert "refused" in theirs and "refused" not in mine and "PENDING" not in mine + theirs
    assert len(mine.strip().splitlines()) == 4 and len(theirs.strip().splitlines()) == 4


def test_the_script_can_narrow_to_one_tool(flow, interleaved, capsys):
    script = channel_audit_script()
    script.main(["--user", USER_OID, "--tool", "client_trend"], repository=flow.world.audit, writers=flow.world.writers)
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and "client_trend" in lines[0] and "client 2001" in lines[0]


# ----------------------------------------------------------- surfaces agree

READS = (
    ("book_rank", {"limit": 8}),
    ("client_resolve", {"name_or_text": "Cascade Retail Partners", "current_client_id": 2001}),
    ("client_situation", {"client_id": 2001}),
    ("claim_cell_history", {"client_id": 2001, "program_code": "GA_JTC", "tax_year": 2023}),
    ("client_trend", {"client_id": 2001}),
    ("client_at_risk", {"client_id": 2001, "tax_year": 2023, "state": "GA", "method": "min_max"}),
    ("client_eligibility", {"client_id": 2001, "tax_year": 2023, "state": "GA", "method": "pay_period"}),
    ("client_discovery", {"client_id": 2001, "state": "GA"}),
    ("findings_list", {"client_id": PAYROLL_CLIENT, "tax_year": 2025, "state": "GA"}),
    ("calc_walkthrough", {"client_id": 2001, "tax_year": 2023, "state": "GA"}),
)


@pytest.mark.parametrize(("tool", "args"), READS, ids=[t for t, _ in READS])
def test_the_same_read_gives_the_same_figures_and_words_on_every_surface(flow, tool, args):
    rest = RestSurface(flow.gw, USER_OID).call(tool, args)
    mcp = McpSurface(flow.gw, USER_OID).call(tool, args)
    via_api = api().post(
        f"/api/capabilities/{tool}", json={"args": args},
        headers={"Authorization": f"Bearer {mint_app()}", "X-TCC-Acting-User": acting_header()},
    ).json()
    direct = registry.call(tool, **args).to_dict()
    assert rest.ok and mcp.ok
    for body in (rest.body, mcp.body, via_api):
        assert body["facts"] == direct["facts"] and body["blocks"] == direct["blocks"] and body["provenance"] == direct["provenance"]
    assert rest.text == mcp.text == render_tool_text(via_api) == render_tool_text(direct), "the words a person reads are the same"


def test_the_portals_own_endpoints_give_the_figures_the_channel_gives(flow):
    http, rest = api(), RestSurface(flow.gw, USER_OID)

    book = rest.call("book_rank", {"limit": 8}).facts["clients"]
    page = http.get("/api/v2/portfolio", params={"sort": "priority", "order": "asc", "limit": 8}, headers=operator_headers()).json()["items"]
    assert [(c["client_name"], c["identified_usd"], c["program_code"]) for c in book] == [
        (r["client_name"], r["identified_usd"], r["program_code"]) for r in page]

    portal = {
        "client_situation": ("/api/v2/clients/2001/situation", {}),
        "claim_cell_history": ("/api/claims/cell/2001/GA_JTC/2023", {}),
        "findings_list": (f"/api/findings/{PAYROLL_CLIENT}/2025", {"state": "GA"}),
    }
    for tool, (path, params) in portal.items():
        args = dict(READS)[tool]
        answer = http.get(path, params=params, headers=operator_headers())
        assert answer.status_code == 200, (tool, answer.text)
        assert rest.call(tool, args).facts == answer.json(), tool

