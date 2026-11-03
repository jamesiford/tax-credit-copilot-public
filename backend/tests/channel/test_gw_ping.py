"""`channel_ping`: the diagnostic for the identity spikes. [CH-06]

Off unless `CHANNEL_DEBUG_WHOAMI` is on. When on it says who the platform believes is
calling and by which rule, echoes the acting-user headers AS RECEIVED, and whether the
API answers — and is audited like any tool. It must never hand a token back.
"""
from __future__ import annotations

import json

import httpx

from gateway_harness import ORCHESTRATOR_APP, USER_OID, agent_headers, agent_token, build_gateway, user_headers

PING = "/channel/v1/tools/channel_ping"


def test_the_diagnostic_does_not_exist_unless_switched_on(gateway):
    assert gateway.client.post(PING, json={}, headers=agent_headers()).status_code == 404
    names = {t["name"] for t in gateway.client.get("/channel/v1/tools", headers=agent_headers()).json()["tools"]}
    assert "channel_ping" not in names


def test_on_it_reports_the_caller_the_rule_the_headers_as_received_and_the_api(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api, debug_whoami=True)
    facts = gw.client.post(PING, json={}, headers=agent_headers()).json()["facts"]
    assert facts["caller_shape"] == "agent" and facts["authorised_by"] == "role" and facts["api_reachable"] is True
    assert facts["gateway_version"]
    assert facts["acting_user_received"] == {
        "x-acting-user-oid": USER_OID, "x-acting-user-name": "Pat Writer", "x-acting-tenant": facts["acting_user_resolved"]["tenant_id"],
        "x-channel": "teams", "x-conversation-id": "conv-1", "x-correlation-id": "corr-1"}
    assert facts["acting_user_resolved"]["assurance"] == "channel-asserted"


def test_it_names_the_allow_list_path_when_that_is_what_let_the_caller_in(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api, debug_whoami=True, allowed_caller_app_ids=(ORCHESTRATOR_APP,))
    facts = gw.client.post(PING, json={}, headers=agent_headers(agent_token(roles=None))).json()["facts"]
    assert facts["authorised_by"] == "allow-list"


def test_it_says_when_the_api_cannot_be_reached(tmp_path):
    def refuse(request):
        raise httpx.ConnectError("no route")

    gw = build_gateway(tmp_path, transport=httpx.MockTransport(refuse), debug_whoami=True)
    assert gw.client.post(PING, json={}, headers=agent_headers()).json()["facts"]["api_reachable"] is False


def test_it_never_returns_a_token_or_an_authorization_header(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api, debug_whoami=True, token_provider=lambda: "SECRET-API-TOKEN")
    token = agent_token()
    response = gw.client.post(PING, json={}, headers=agent_headers(token))
    text = response.text
    assert token not in text and "SECRET-API-TOKEN" not in text and "Bearer" not in text and "eyJ" not in text
    assert "authorization" not in json.dumps(response.json()).lower()


def test_it_is_audited_like_any_read(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api, debug_whoami=True)
    gw.client.post(PING, json={}, headers=user_headers())
    assert [(e.tool_name, e.phase, e.outcome) for e in gw.events()] == [("channel_ping", "begin", "pending"), ("channel_ping", "end", "ok")]


def test_it_rejects_arguments(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api, debug_whoami=True)
    assert gw.client.post(PING, json={"args": {"x": 1}}, headers=agent_headers()).status_code == 422
