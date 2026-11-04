"""The MCP facade is a standard Streamable-HTTP MCP server, and the SDK's own client proves it. [RM-14]

`channel/mcp.py` is hand-written (D-65, D-136): every call must pass through the gateway's one pipeline and a session
must belong to the person who opened it, which the `mcp` SDK's server does not give (RM-14 measured it on 2.3.0). A
hand-written server is only acceptable if it is provably standard, so this file holds it to the specification in two
ways:

* the installed SDK's CLIENT (`mcp.Client` over `streamable_http_client`, through an in-process ASGI transport) connects,
  negotiates, lists and calls, in both connection modes, as any real client would;
* each rule of the Streamable HTTP transport and of JSON-RPC 2.0 that the facade implements is a test: version
  negotiation, the session id, the protocol-version header, Origin, the error codes, 202 for a notification, the
  difference between a protocol error (a JSON-RPC error) and a tool failure (`isError`).

`test_gw_mcp.py` keeps the facade's own guarantees (one pipeline, same audit as REST, platform-rendered text, sessions
bound to a person); this file is only about being a standard server.
"""
from __future__ import annotations

import asyncio

import httpx2
import pytest
from mcp import Client, MCPError, types
from mcp.client.streamable_http import streamable_http_client

from application.capabilities import catalog
from channel.mcp import PROTOCOL_VERSIONS
from channel.render import VERBATIM
from gateway_harness import OTHER_OID, agent_headers, agent_token, build_gateway, user_headers, user_token

MCP = "/mcp"
ORIGIN = "https://cowork.example.test"


def rpc(method, params=None, id=1):
    body = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    return {**body, "id": id} if id is not None else body


def initialize(gw, headers=None, version="2025-06-18"):
    response = gw.client.post(MCP, json=rpc("initialize", {"protocolVersion": version}), headers=headers or user_headers())
    return response, response.headers.get("mcp-session-id")


def session_headers(session, **extra):
    return {**user_headers(), "Mcp-Session-Id": session, **extra}


# ----------------------------------------------------------------------- the SDK's own client


def with_sdk_client(gw, body, mode="legacy", token=None):
    """Run `body(client, seen)` with the SDK client connected to the facade; `seen` holds the session ids the server issued."""
    seen: list[str] = []

    async def remember(response):
        if sid := response.headers.get("mcp-session-id"):
            seen.append(sid)

    async def go():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=gw.client.app), base_url="http://testserver",
            headers={"Authorization": f"Bearer {token or user_token()}"}, event_hooks={"response": [remember]},
        ) as http:
            async with Client(streamable_http_client("http://testserver/mcp", http_client=http), mode=mode) as client:
                return await body(client, seen)

    return asyncio.run(go())


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_the_sdk_client_negotiates_with_the_facade_in_both_connection_modes(gateway, mode):
    async def body(client, seen):
        return client.protocol_version, client.server_info, client.server_capabilities, client.instructions

    version, info, capabilities, instructions = with_sdk_client(gateway, body, mode)
    assert version == PROTOCOL_VERSIONS[0] == "2025-11-25"
    assert (info.name, info.version) == ("tcc-channel-gateway", "0.1.0")
    assert capabilities.tools is not None and capabilities.tools.list_changed is False
    assert capabilities.resources is None and capabilities.prompts is None and capabilities.logging is None
    assert "exactly as written" in instructions


def test_the_sdk_client_lists_the_catalog_with_its_schemas_descriptions_and_hints(gateway):
    async def body(client, seen):
        return (await client.list_tools()).tools

    tools = with_sdk_client(gateway, body)
    expected = catalog.offered_for_channel()
    assert [t.name for t in tools] == [s.name for s in expected]
    for tool, spec in zip(tools, expected):
        hints = catalog.behaviour_hints(spec)
        assert tool.input_schema == spec.schema and tool.description == catalog.channel_description(spec)
        assert (tool.annotations.read_only_hint, tool.annotations.destructive_hint, tool.annotations.idempotent_hint,
                tool.annotations.open_world_hint) == (hints["readOnlyHint"], hints["destructiveHint"], hints["idempotentHint"], False)


def test_the_sdk_client_calls_a_tool_and_gets_the_envelope_and_the_platforms_text(gateway):
    async def body(client, seen):
        return await client.call_tool("client_situation", {"client_id": 2001})

    result = with_sdk_client(gateway, body)
    assert result.is_error is False and result.content[0].text.startswith(VERBATIM)
    assert result.structured_content["tool"] == "client_situation" and result.structured_content["facts"]["credit"]


def test_a_tool_that_fails_is_an_error_result_and_an_unknown_tool_is_a_protocol_error(gateway, fake_api):
    fake_api.replies["client_situation"] = (409, {"error": {"code": "not_calculated", "message": "no run", "retryable": False}})

    async def body(client, seen):
        failed = await client.call_tool("client_situation", {"client_id": 2001})
        with pytest.raises(MCPError) as unknown:
            await client.call_tool("drop_tables", {})
        return failed, unknown.value

    failed, unknown = with_sdk_client(gateway, body)
    assert failed.is_error is True and "not_calculated" in failed.content[0].text
    assert unknown.code == types.INVALID_PARAMS and "unknown tool" in unknown.message


def test_the_sdk_clients_session_is_the_conversation_and_ends_when_it_closes(gateway):
    async def body(client, seen):
        await client.call_tool("client_situation", {"client_id": 2001})
        await client.call_tool("client_trend", {"client_id": 2001})
        return list(seen)

    issued = with_sdk_client(gateway, body)
    assert len(set(issued)) == 1, "one initialize, one session id"
    assert {e.conversation_id for e in gateway.events() if e.tool_name != "initialize"} == {issued[0]}
    after = gateway.client.post(MCP, json=rpc("tools/list"), headers=session_headers(issued[0]))
    assert after.status_code == 404, "the client's DELETE on close ended the session"


# -------------------------------------------------------------- initialize and version negotiation


@pytest.mark.parametrize("version", PROTOCOL_VERSIONS)
def test_a_supported_version_is_answered_with_itself(gateway, version):
    response, _ = initialize(gateway, version=version)
    assert response.json()["result"]["protocolVersion"] == version


@pytest.mark.parametrize("asked", ["1999-01-01", "2026-07-28", "nonsense", 7, None])
def test_an_unsupported_version_is_answered_with_the_newest_the_server_speaks(gateway, asked):
    response = gateway.client.post(MCP, json=rpc("initialize", {"protocolVersion": asked}), headers=user_headers())
    assert response.json()["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_the_initialize_result_and_the_session_id_have_the_shape_the_specification_gives(gateway):
    response, session = initialize(gateway)
    result = response.json()["result"]
    assert set(result) == {"protocolVersion", "capabilities", "serverInfo", "instructions"}
    assert result["capabilities"] == {"tools": {"listChanged": False}} and set(result["serverInfo"]) == {"name", "version"}
    assert session and all(0x21 <= ord(c) <= 0x7E for c in session), "a session id is visible ASCII"
    assert initialize(gateway)[1] != session, "every initialize opens a new session"


def test_a_client_that_omits_the_protocol_version_is_answered_with_the_newest(gateway):
    response = gateway.client.post(MCP, json=rpc("initialize"), headers=user_headers())
    assert response.status_code == 200 and response.json()["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0]


# ----------------------------------------------------------------------------- JSON-RPC 2.0 shape


@pytest.mark.parametrize("request_id", [1, 0, 7, "abc", "7"])
def test_a_response_echoes_the_request_id_and_carries_exactly_one_of_result_and_error(gateway, request_id):
    _, session = initialize(gateway)
    for method, kind in (("ping", "result"), ("tools/list", "result"), ("resources/list", "error")):
        body = gateway.client.post(MCP, json=rpc(method, id=request_id), headers=session_headers(session)).json()
        assert body["jsonrpc"] == "2.0" and body["id"] == request_id and type(body["id"]) is type(request_id)
        assert (kind in body) and (({"result", "error"} - {kind}).isdisjoint(body))


def test_every_answer_is_one_json_document_never_a_stream(gateway):
    _, session = initialize(gateway)
    for body in (rpc("ping"), rpc("tools/list"), rpc("resources/list")):
        response = gateway.client.post(MCP, json=body, headers=session_headers(session, Accept="application/json, text/event-stream"))
        assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("notification", [
    rpc("notifications/initialized", id=None), rpc("notifications/cancelled", {"requestId": 1}, id=None),
    rpc("notifications/some-future-thing", id=None),
], ids=["initialized", "cancelled", "unknown"])
def test_a_notification_is_acknowledged_with_202_and_no_body(gateway, notification):
    _, session = initialize(gateway)
    response = gateway.client.post(MCP, json=notification, headers=session_headers(session))
    assert response.status_code == 202 and response.content == b""


def test_a_client_response_is_acknowledged_with_202_because_the_server_never_asks_anything(gateway):
    _, session = initialize(gateway)
    for message in ({"jsonrpc": "2.0", "id": 9, "result": {}}, {"jsonrpc": "2.0", "id": 9, "error": {"code": -32601, "message": "no"}}):
        response = gateway.client.post(MCP, json=message, headers=session_headers(session))
        assert response.status_code == 202 and response.content == b""


# ------------------------------------------------------------------------------------ errors


def test_the_error_codes_are_the_sdks_and_the_specifications(gateway):
    from channel import mcp

    assert (mcp._PARSE_ERROR, mcp._INVALID_REQUEST, mcp._METHOD_NOT_FOUND, mcp._INVALID_PARAMS) == (
        types.PARSE_ERROR, types.INVALID_REQUEST, types.METHOD_NOT_FOUND, types.INVALID_PARAMS) == (-32700, -32600, -32601, -32602)


def test_unparseable_json_is_a_parse_error_with_a_null_id_and_a_400(gateway):
    response = gateway.client.post(MCP, content=b"{{", headers={**user_headers(), "Content-Type": "application/json"})
    assert response.status_code == 400 and response.json() == {
        "jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "the body is not JSON"}}
    assert gateway.client.post(MCP, content=b"\xff\xfe", headers={**user_headers(), "Content-Type": "application/json"}).json()["error"]["code"] == -32700


@pytest.mark.parametrize("message", [
    [rpc("ping")], [], "ping", 7, {"method": "ping", "id": 1}, {**rpc("ping"), "jsonrpc": "1.0"}, {**rpc("ping"), "method": 5},
    {"jsonrpc": "2.0", "id": 1}, {**rpc("ping"), "id": None}, {**rpc("ping"), "id": True}, {**rpc("ping"), "id": 1.5}, {**rpc("ping"), "id": [1]},
], ids=["batch", "empty-batch", "string", "number", "no-jsonrpc", "old-jsonrpc", "method-not-a-string", "no-method",
        "null-id", "bool-id", "float-id", "array-id"])
def test_a_message_that_is_not_a_json_rpc_request_is_an_invalid_request_and_a_400(gateway, message):
    _, session = initialize(gateway)
    response = gateway.client.post(MCP, json=message, headers=session_headers(session))
    assert response.status_code == 400 and response.json()["error"]["code"] == -32600 and response.json()["id"] is None


def test_json_null_is_an_invalid_request_and_an_empty_body_is_a_parse_error(gateway):
    _, session = initialize(gateway)
    headers = {**session_headers(session), "Content-Type": "application/json"}
    assert gateway.client.post(MCP, content=b"null", headers=headers).json()["error"]["code"] == -32600
    assert gateway.client.post(MCP, content=b"", headers=headers).json()["error"]["code"] == -32700


def test_an_unknown_method_is_method_not_found_with_the_id_and_a_200(gateway):
    _, session = initialize(gateway)
    for method in ("resources/list", "prompts/list", "completion/complete", "logging/setLevel", "server/discover", "tools/nope"):
        response = gateway.client.post(MCP, json=rpc(method, id=4), headers=session_headers(session))
        assert response.status_code == 200 and response.json()["id"] == 4 and response.json()["error"]["code"] == -32601, method


@pytest.mark.parametrize("params", [{}, {"arguments": {}}, {"name": 5}, {"name": ["x"]}, {"name": "client_situation", "arguments": "x"},
                                    {"name": "client_situation", "arguments": [1]}, [1], "x", {"name": "no_such_tool"}])
def test_a_bad_tools_call_is_invalid_params_not_a_tool_error(gateway, params):
    _, session = initialize(gateway)
    response = gateway.client.post(MCP, json=rpc("tools/call", params), headers=session_headers(session))
    assert response.status_code == 200 and response.json()["error"]["code"] == -32602 and "result" not in response.json()


def test_a_tool_that_failed_is_a_result_with_is_error_never_a_json_rpc_error(gateway, fake_api):
    fake_api.replies["client_situation"] = (422, {"error": {"code": "invalid_arguments", "message": "no", "retryable": False}})
    _, session = initialize(gateway)
    response = gateway.client.post(MCP, json=rpc("tools/call", {"name": "client_situation", "arguments": {"client_id": 2001}}),
                                   headers=session_headers(session))
    body = response.json()
    assert response.status_code == 200 and "error" not in body and body["result"]["isError"] is True
    assert body["result"]["content"][0]["type"] == "text" and body["result"]["structuredContent"]["error"]["code"] == "invalid_arguments"


def test_null_params_and_null_arguments_are_taken_as_empty(gateway):
    _, session = initialize(gateway)
    assert "result" in gateway.client.post(MCP, json={**rpc("ping"), "params": None}, headers=session_headers(session)).json()
    called = gateway.client.post(MCP, json=rpc("tools/call", {"name": "book_rank", "arguments": None}), headers=session_headers(session)).json()
    assert called["result"]["isError"] is False


def test_tools_list_pages_nothing_and_ignores_a_cursor(gateway):
    _, session = initialize(gateway)
    result = gateway.client.post(MCP, json=rpc("tools/list", {"cursor": "x"}), headers=session_headers(session)).json()["result"]
    assert set(result) == {"tools"} and len(result["tools"]) == len(catalog.offered_for_channel())
    assert all(t["inputSchema"]["type"] == "object" and {"name", "description", "annotations"} <= set(t) for t in result["tools"])


# --------------------------------------------------------------------------------- the session


def test_a_request_with_no_session_id_is_a_400_and_one_with_an_unknown_id_is_a_404_with_the_ids_error(gateway):
    missing = gateway.client.post(MCP, json=rpc("tools/list", id=3), headers=user_headers())
    assert missing.status_code == 400 and missing.json()["id"] == 3 and missing.json()["error"]["code"] == -32600
    unknown = gateway.client.post(MCP, json=rpc("tools/list", id=4), headers=session_headers("not-a-session"))
    assert unknown.status_code == 404 and unknown.json()["id"] == 4 and unknown.json()["error"]["code"] == -32600
    assert "initialise" in unknown.json()["error"]["message"], "the 404 tells a client what to do"


def test_another_persons_session_id_is_unknown_not_forbidden(gateway):
    _, session = initialize(gateway)
    other = {**user_headers(user_token(oid=OTHER_OID)), "Mcp-Session-Id": session}
    assert gateway.client.post(MCP, json=rpc("tools/list"), headers=other).status_code == 404
    assert gateway.client.delete(MCP, headers=other).status_code == 404
    assert gateway.client.post(MCP, json=rpc("tools/list"), headers=session_headers(session)).status_code == 200


def test_delete_ends_only_the_callers_own_session(gateway):
    _, session = initialize(gateway)
    assert gateway.client.delete(MCP, headers=user_headers()).status_code == 404, "no session id: nothing to end"
    assert gateway.client.delete(MCP, headers=session_headers("nope")).status_code == 404
    assert gateway.client.delete(MCP, headers=session_headers(session)).status_code == 200
    assert gateway.client.post(MCP, json=rpc("ping"), headers=session_headers(session)).status_code == 404
    assert gateway.client.delete(MCP, headers=session_headers(session)).status_code == 404


def test_the_server_offers_no_stream_and_no_other_method(gateway):
    get = gateway.client.get(MCP, headers={**user_headers(), "Accept": "text/event-stream"})
    assert get.status_code == 405 and get.headers["allow"] == "POST, DELETE"
    assert gateway.client.put(MCP, json=rpc("ping"), headers=user_headers()).status_code == 405
    assert gateway.client.patch(MCP, json=rpc("ping"), headers=user_headers()).status_code == 405


# ------------------------------------------------------------------- MCP-Protocol-Version header


@pytest.mark.parametrize("version", PROTOCOL_VERSIONS)
def test_a_supported_protocol_version_header_is_accepted_and_none_is_accepted_too(gateway, version):
    _, session = initialize(gateway)
    assert gateway.client.post(MCP, json=rpc("ping"), headers=session_headers(session, **{"MCP-Protocol-Version": version})).status_code == 200
    assert gateway.client.post(MCP, json=rpc("ping"), headers=session_headers(session)).status_code == 200


@pytest.mark.parametrize("version", ["1999-01-01", "2026-07-28", "latest", ""])
def test_an_unsupported_protocol_version_header_is_a_400_on_a_request_and_a_notification(gateway, version):
    _, session = initialize(gateway)
    headers = session_headers(session, **{"MCP-Protocol-Version": version})
    for message in (rpc("ping"), rpc("notifications/initialized", id=None)):
        response = gateway.client.post(MCP, json=message, headers=headers)
        assert response.status_code == 400 and response.json()["error"]["code"] == -32600


def test_initialize_is_not_held_to_a_version_header_because_it_is_where_the_version_is_chosen(gateway):
    response = gateway.client.post(MCP, json=rpc("initialize", {"protocolVersion": "2025-06-18"}),
                                   headers={**user_headers(), "MCP-Protocol-Version": "1999-01-01"})
    assert response.status_code == 200


# ----------------------------------------------------------------------------------- Origin


def test_a_request_with_no_origin_is_served_because_an_mcp_client_is_not_a_browser(gateway):
    assert initialize(gateway)[0].status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:3000", ORIGIN])
def test_an_origin_that_is_not_allowed_is_a_403_on_every_method_even_with_a_valid_token(gateway, origin):
    headers = {**user_headers(), "Origin": origin}
    for response in (gateway.client.post(MCP, json=rpc("initialize"), headers=headers), gateway.client.get(MCP, headers=headers),
                     gateway.client.delete(MCP, headers=headers)):
        assert response.status_code == 403 and response.json()["error"]["code"] == "origin_not_allowed"
    assert not gateway.events(), "a refused origin reached no tool, no audit and no session"


def test_the_origin_is_checked_before_the_token_is_read(gateway):
    response = gateway.client.post(MCP, json=rpc("initialize"), headers={"Origin": "https://evil.example"})
    assert response.status_code == 403, "a request from a web page learns nothing about whether its token would have worked"


@pytest.mark.parametrize("sent", [ORIGIN, ORIGIN.upper(), ORIGIN + "/", " " + ORIGIN])
def test_an_allowed_origin_is_served_however_it_is_written(tmp_path, sent):
    gw = build_gateway(tmp_path, mcp_allowed_origins=(ORIGIN,))
    response = gw.client.post(MCP, json=rpc("initialize"), headers={**user_headers(), "Origin": sent})
    assert response.status_code == 200
    assert gw.client.post(MCP, json=rpc("initialize"), headers={**user_headers(), "Origin": "https://evil.example"}).status_code == 403


# ------------------------------------------------------------------------------------- auth


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not.a.jwt"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}],
                         ids=["none", "garbage", "wrong-scheme", "empty"])
def test_no_valid_token_is_a_401_that_names_the_scheme_on_every_method(gateway, headers):
    for response in (gateway.client.post(MCP, json=rpc("initialize"), headers=headers),
                     gateway.client.post(MCP, json=rpc("notifications/initialized", id=None), headers=headers),
                     gateway.client.delete(MCP, headers=headers)):
        assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "unauthenticated"


def test_a_token_without_the_scope_is_a_403_and_an_agent_without_a_person_is_a_400(gateway):
    scopeless = gateway.client.post(MCP, json=rpc("initialize"), headers=user_headers(user_token(scp="Something.Else")))
    assert scopeless.status_code == 403 and scopeless.json()["error"]["code"] == "missing_scope" and "www-authenticate" not in scopeless.headers
    nobody = gateway.client.post(MCP, json=rpc("initialize"), headers=agent_headers(oid=None))
    assert nobody.status_code == 400 and nobody.json()["error"]["code"] == "invalid_acting_user"
    assert gateway.client.post(MCP, json=rpc("initialize"), headers=agent_headers(agent_token())).status_code == 200


def test_an_oversized_body_is_a_413_before_anything_is_parsed(gateway):
    response = gateway.client.post(MCP, content=b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + b"a" * 70_000 + b'"}}',
                                   headers={**user_headers(), "Content-Type": "application/json"})
    assert response.status_code == 413 and response.json()["error"]["code"] == "request_too_large"


def test_an_unknown_tool_in_a_list_the_catalog_does_not_offer_is_not_callable_even_when_it_exists(gateway):
    _, session = initialize(gateway)
    for hidden in ("claim_package_redeem", "channel_ping"):
        response = gateway.client.post(MCP, json=rpc("tools/call", {"name": hidden, "arguments": {}}), headers=session_headers(session))
        assert response.json()["error"]["code"] == -32602, hidden


# ----------------------------------------------------------------------- CHANNEL_MCP_ALLOWED_ORIGINS


def test_the_origin_setting_defaults_to_none_and_is_normalised_and_deduplicated():
    from channel.config import load_settings
    from gateway_harness import API_AUDIENCE, GATEWAY_AUDIENCE, TENANT

    env = {"TENANT_ID": TENANT, "GATEWAY_AUDIENCE": GATEWAY_AUDIENCE, "API_BASE_URL": "https://api.example.test", "API_AUDIENCE": API_AUDIENCE}
    assert load_settings(env).mcp_allowed_origins == ()
    listed = {**env, "CHANNEL_MCP_ALLOWED_ORIGINS": " HTTPS://Cowork.Example.Test/ , https://cowork.example.test, http://localhost:3000"}
    assert load_settings(listed).mcp_allowed_origins == ("https://cowork.example.test", "http://localhost:3000")


@pytest.mark.parametrize("bad", ["*", "cowork.example.test", "https://cowork.example.test/mcp", "https://*.example.test", "ftp://x.example"])
def test_a_malformed_origin_stops_the_gateway_from_starting(bad):
    from channel.config import GatewayConfigurationError, load_settings
    from gateway_harness import API_AUDIENCE, GATEWAY_AUDIENCE, TENANT

    env = {"TENANT_ID": TENANT, "GATEWAY_AUDIENCE": GATEWAY_AUDIENCE, "API_BASE_URL": "https://api.example.test", "API_AUDIENCE": API_AUDIENCE,
           "CHANNEL_MCP_ALLOWED_ORIGINS": bad}
    with pytest.raises(GatewayConfigurationError, match="CHANNEL_MCP_ALLOWED_ORIGINS"):
        load_settings(env)
