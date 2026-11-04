"""The MCP facade: the same tools, the same pipeline. [CH-06]

Cowork's door must not be a side door. So: the tool list IS the catalog with the right
behaviour hints; a call goes through the same audit as REST (compared event for event);
the text a model reads is platform-rendered, starts with the verbatim instruction and
ends with the disclaimer; and sessions belong to the user who opened them.
"""
from __future__ import annotations

from application.capabilities import catalog
from application.capabilities.envelope import DISCLAIMER
from channel.mcp import PREVIEW_SENTENCE, PROTOCOL_VERSIONS
from channel.render import VERBATIM
from gateway_harness import OTHER_OID, agent_headers, user_headers, user_token

MCP = "/mcp"


def rpc(method, params=None, id=1):
    body = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    return {**body, "id": id} if id is not None else body


def open_session(gw, headers=None):
    response = gw.client.post(MCP, json=rpc("initialize", {"protocolVersion": "2025-06-18"}), headers=headers or user_headers())
    assert response.status_code == 200, response.text
    return response.headers["mcp-session-id"], response.json()["result"]


def call(gw, session, name, arguments=None, headers=None):
    return gw.client.post(
        MCP, json=rpc("tools/call", {"name": name, "arguments": arguments or {}}),
        headers={**(headers or user_headers()), "Mcp-Session-Id": session})


# ------------------------------------------------------------------- the protocol


def test_initialize_negotiates_a_version_and_opens_a_session(gateway):
    session, result = open_session(gateway)
    assert session and result["protocolVersion"] == "2025-06-18" and result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "tcc-channel-gateway" and "exactly as written" in result["instructions"]


def test_an_unknown_protocol_version_is_answered_with_the_newest_we_speak(gateway):
    response = gateway.client.post(MCP, json=rpc("initialize", {"protocolVersion": "1999-01-01"}), headers=user_headers())
    assert response.json()["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_a_notification_is_accepted_with_no_body(gateway):
    session, _ = open_session(gateway)
    response = gateway.client.post(MCP, json=rpc("notifications/initialized", id=None), headers={**user_headers(), "Mcp-Session-Id": session})
    assert response.status_code == 202 and response.content == b""


def test_ping_and_unknown_methods(gateway):
    session, _ = open_session(gateway)
    headers = {**user_headers(), "Mcp-Session-Id": session}
    assert gateway.client.post(MCP, json=rpc("ping"), headers=headers).json()["result"] == {}
    assert gateway.client.post(MCP, json=rpc("resources/list"), headers=headers).json()["error"]["code"] == -32601


def test_the_server_opens_no_stream_to_the_client(gateway):
    response = gateway.client.get(MCP, headers=user_headers())
    assert response.status_code == 405 and "POST" in response.headers["allow"]


def test_garbage_is_a_protocol_error_not_a_crash(gateway):
    assert gateway.client.post(MCP, content="{{", headers={**user_headers(), "Content-Type": "application/json"}).json()["error"]["code"] == -32700
    assert gateway.client.post(MCP, json=[rpc("ping")], headers=user_headers()).status_code == 400


def test_no_token_is_a_401_here_too(gateway):
    assert gateway.client.post(MCP, json=rpc("initialize")).status_code == 401


def test_the_session_is_the_conversation_and_belongs_to_one_user(gateway):
    session, _ = open_session(gateway)
    other = {**user_headers(user_token(oid=OTHER_OID)), "Mcp-Session-Id": session}
    assert gateway.client.post(MCP, json=rpc("tools/list"), headers=other).status_code == 404
    assert gateway.client.post(MCP, json=rpc("tools/list"), headers={**user_headers(), "Mcp-Session-Id": "nope"}).status_code == 404
    assert gateway.client.post(MCP, json=rpc("tools/list"), headers=user_headers()).status_code == 400, "no session id at all is a 400 (RM-14); an unknown one is a 404"


def test_a_session_can_be_ended_by_its_owner_only(gateway):
    session, _ = open_session(gateway)
    assert gateway.client.delete(MCP, headers={**user_headers(user_token(oid=OTHER_OID)), "Mcp-Session-Id": session}).status_code == 404
    assert gateway.client.delete(MCP, headers={**user_headers(), "Mcp-Session-Id": session}).status_code == 200
    assert gateway.client.post(MCP, json=rpc("tools/list"), headers={**user_headers(), "Mcp-Session-Id": session}).status_code == 404


# ---------------------------------------------------------------------- the list


def test_tools_list_is_the_catalog_with_schemas_and_annotations(gateway):
    session, _ = open_session(gateway)
    tools = gateway.client.post(MCP, json=rpc("tools/list"), headers={**user_headers(), "Mcp-Session-Id": session}).json()["result"]["tools"]
    assert {t["name"] for t in tools} == {s.name for s in catalog.offered()}
    for tool in tools:
        spec = catalog.get(tool["name"])
        assert tool["inputSchema"] == spec.schema and tool["description"].startswith(spec.description)
        hints = tool["annotations"]
        assert hints["openWorldHint"] is False
        assert hints["readOnlyHint"] is (spec.kind == catalog.READ)
        assert hints["destructiveHint"] is (spec.kind == catalog.WRITE_COMMIT)
        if spec.kind == catalog.WRITE_COMMIT:
            assert hints["idempotentHint"] is False


def test_writes_are_the_two_step_pair_and_the_descriptions_say_so(gateway):
    session, _ = open_session(gateway)
    tools = {t["name"]: t for t in gateway.client.post(
        MCP, json=rpc("tools/list"), headers={**user_headers(), "Mcp-Session-Id": session}).json()["result"]["tools"]}
    for base in ("finding_resolve", "claim_transition", "engagement_set", "claim_package_create"):
        assert PREVIEW_SENTENCE in tools[f"{base}_prepare"]["description"]
        assert "confirmed" in tools[f"{base}_commit"]["description"]
    assert "channel_ping" not in tools and "claim_package_redeem" not in tools


# ---------------------------------------------------------------------- the call


def test_a_call_returns_platform_text_the_envelope_and_the_disclaimer(gateway):
    session, _ = open_session(gateway)
    result = call(gateway, session, "client_situation", {"client_id": 2001}).json()["result"]
    text = result["content"][0]["text"]
    assert result["isError"] is False and text.startswith(VERBATIM) and text.endswith(DISCLAIMER)
    assert "The credit is $31,500.00." in text
    assert result["structuredContent"]["tool"] == "client_situation" and result["structuredContent"]["correlation_id"]


def test_a_refusal_is_an_error_result_not_a_protocol_error(gateway, fake_api):
    fake_api.replies["client_situation"] = (409, {"error": {"code": "not_calculated", "message": "no run", "retryable": False}})
    session, _ = open_session(gateway)
    result = call(gateway, session, "client_situation", {"client_id": 2001}).json()["result"]
    assert result["isError"] is True and "not_calculated" in result["content"][0]["text"]


def test_an_unknown_tool_is_an_invalid_params_error(gateway):
    session, _ = open_session(gateway)
    assert call(gateway, session, "drop_tables").json()["error"]["code"] == -32602
    assert call(gateway, session, "client_situation", "not-an-object").status_code == 200


def test_the_prepare_text_hands_the_model_the_token_to_commit_with(gateway, fake_api):
    from gateway_harness import envelope

    fake_api.replies["engagement_set_prepare"] = (200, envelope("engagement_set_prepare", {
        "preview": {}, "confirmation": {"token": "the-token-value", "expires_at": "x"}}))
    session, _ = open_session(gateway)
    text = call(gateway, session, "engagement_set_prepare", {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope"}
                ).json()["result"]["content"][0]["text"]
    assert "the-token-value" in text and "only after the user confirms" in text


def test_the_mcp_session_is_the_conversation_for_the_ledger_and_the_audit(gateway):
    session, _ = open_session(gateway)
    call(gateway, session, "client_situation", {"client_id": 2001})
    assert {e.conversation_id for e in gateway.events()} == {session}
    assert {e.channel for e in gateway.events()} == {"cowork"} and {e.identity_assurance for e in gateway.events()} == {"delegated"}
    assert gateway.ledger.facts_for(session)


def test_an_agent_may_use_the_facade_too_with_its_headers(gateway):
    headers = agent_headers()
    response = gateway.client.post(MCP, json=rpc("initialize"), headers=headers)
    assert response.status_code == 200


# ---------------------------------------------------- identical to the REST path


def _trail(gw):
    return [(e.tool_name, e.phase, e.outcome, e.action_kind, e.run_id, e.trail_sha256, e.numeric_guard,
             e.request_sha256, e.client_id) for e in gw.events()]


def test_mcp_and_rest_leave_the_same_trail_for_success_failure_and_refusal(tmp_path, fake_api):
    from gateway_harness import build_gateway

    scenarios = [
        ("client_situation", {"client_id": 2001}, None),
        ("client_situation", {"client_id": 2001}, (409, {"error": {"code": "not_calculated", "message": "no", "retryable": False}})),
        ("client_situation", {"client_id": 2001}, (403, {"error": {"code": "not_authorized", "message": "no", "retryable": False}})),
        ("engagement_set_commit", {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope"},
         (422, {"error": {"code": "invalid_arguments", "message": "no", "retryable": False}})),
    ]
    for index, (tool, args, reply) in enumerate(scenarios):
        trails = {}
        for door in ("rest", "mcp"):
            directory = tmp_path / f"{index}-{door}"
            directory.mkdir()
            gw = build_gateway(directory, api=fake_api)
            fake_api.replies.clear()
            if reply:
                fake_api.replies[tool] = reply
            if door == "rest":
                gw.client.post(f"/channel/v1/tools/{tool}", json={"args": args}, headers=user_headers())
            else:
                session, _ = open_session(gw)
                call(gw, session, tool, args)
            trails[door] = _trail(gw)
        assert trails["rest"] == trails["mcp"], (tool, reply)
