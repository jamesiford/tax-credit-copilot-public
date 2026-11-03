"""The gateway names a Teams user from the directory, and only when it must. [CH-15a]

An agent caller (Teams, Copilot Chat) carries an object id and, from the orchestrator,
the placeholder `(name not provided)`. With `CHANNEL_RESOLVE_DISPLAY_NAMES` on, the
gateway asks the directory once and the person's name and UPN reach the audit columns
and the API, where the UPN becomes the author of a write. A Cowork caller already
carries a name from its token and never reaches Graph. Everything is fail-soft: no
answer means the request carries on exactly as it would have.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from application import channel_wiring
from application.display_names import PLACEHOLDER_NAME, ResolvedPerson
from channel.config import load_settings
from gateway_harness import (
    API_AUDIENCE, GATEWAY_AUDIENCE, TENANT, USER_OID, agent_headers, build_gateway, user_headers,
)
from infrastructure.auth.graph_people import GraphDisplayNameResolver
from test_gw_mcp import call, open_session

CALL = "/channel/v1/tools/client_situation"
ARGS = {"args": {"client_id": 2001}}
COMMIT = "/channel/v1/tools/engagement_set_commit"
WRITE = {"args": {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope"}}
NARRATION = "/channel/v1/audit/narration"
PAT = ResolvedPerson("Pat Example", "pat@example.test")


class FakeResolver:
    def __init__(self, answer=PAT, error: Exception | None = None) -> None:
        self.answer, self.error, self.asked = answer, error, []

    def resolve(self, oid: str):
        self.asked.append(oid)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def resolver():
    fake = FakeResolver()
    channel_wiring.set_display_name_resolver(fake)
    yield fake
    channel_wiring.set_display_name_resolver(None)


def placeholder_headers(**over):
    return agent_headers(name=PLACEHOLDER_NAME, **over)


def on(tmp_path, fake_api, **kwargs):
    return build_gateway(tmp_path, api=fake_api, resolve_display_names=True, **kwargs)


# ---------------------------------------------------------------- configuration


ENV = {"TENANT_ID": TENANT, "GATEWAY_AUDIENCE": GATEWAY_AUDIENCE, "API_BASE_URL": "https://api.example.test",
       "API_AUDIENCE": API_AUDIENCE}


@pytest.mark.parametrize("value, expected", [(None, False), ("", False), ("false", False), ("true", True), ("True", True), ("1", True)])
def test_the_switch_is_off_unless_asked_for(value, expected):
    env = ENV if value is None else {**ENV, "CHANNEL_RESOLVE_DISPLAY_NAMES": value}
    assert load_settings(env).resolve_display_names is expected


def test_with_the_switch_off_graph_is_never_asked(tmp_path, fake_api, resolver):
    gw = build_gateway(tmp_path, api=fake_api)
    assert gw.client.post(CALL, json=ARGS, headers=placeholder_headers()).status_code == 200
    assert resolver.asked == []
    assert {e.user_display_name for e in gw.events()} == {PLACEHOLDER_NAME}
    assert fake_api.calls[0]["acting"].upn is None


# ------------------------------------------------------------------- where it applies


def test_a_placeholder_name_is_replaced_in_the_audit_rows_and_the_apis_header(tmp_path, fake_api, resolver):
    gw = on(tmp_path, fake_api)
    assert gw.client.post(CALL, json=ARGS, headers=placeholder_headers()).status_code == 200
    assert resolver.asked == [USER_OID]
    events = gw.events()
    assert events and {(e.user_display_name, e.user_upn) for e in events} == {("Pat Example", "pat@example.test")}
    acting = fake_api.calls[0]["acting"]
    assert (acting.display_name, acting.upn, acting.assurance) == ("Pat Example", "pat@example.test", "channel-asserted")


def test_a_real_name_from_the_channel_is_left_alone(tmp_path, fake_api, resolver):
    gw = on(tmp_path, fake_api)
    gw.client.post(CALL, json=ARGS, headers=agent_headers(name="Pat From Teams"))
    assert resolver.asked == []
    assert {e.user_display_name for e in gw.events()} == {"Pat From Teams"}


def test_a_write_is_authored_by_the_upn(tmp_path, fake_api, resolver):
    gw = on(tmp_path, fake_api)
    assert gw.client.post(COMMIT, json=WRITE, headers=placeholder_headers()).status_code == 200
    assert fake_api.calls[0]["acting"].actor == "pat@example.test"


def test_without_a_resolved_name_a_write_is_authored_by_the_oid_as_before(tmp_path, fake_api):
    channel_wiring.set_display_name_resolver(FakeResolver(None))
    try:
        gw = on(tmp_path, fake_api)
        assert gw.client.post(COMMIT, json=WRITE, headers=placeholder_headers()).status_code == 200
    finally:
        channel_wiring.set_display_name_resolver(None)
    assert fake_api.calls[0]["acting"].actor == USER_OID


def test_the_narration_row_names_the_person_too(tmp_path, fake_api, resolver):
    import hashlib

    gw = on(tmp_path, fake_api)
    body = {"agent_name": "ChannelNarratorAgent", "prompt_sha256": hashlib.sha256(b"p").hexdigest(),
            "guard_status": "pass", "violations_count": 0}
    assert gw.client.post(NARRATION, json=body, headers=placeholder_headers()).status_code == 200
    (event,) = [e for e in gw.events() if e.action_kind == "narrate"]
    assert (event.user_display_name, event.user_upn) == ("Pat Example", "pat@example.test")
    assert gw.actions.recent()[0].user_upn == "pat@example.test"


def test_the_mcp_door_names_an_agent_caller_the_same_way(tmp_path, fake_api, resolver):
    gw = on(tmp_path, fake_api)
    session, _ = open_session(gw, placeholder_headers())
    assert call(gw, session, "client_situation", {"client_id": 2001}, placeholder_headers()).status_code == 200
    assert fake_api.calls[0]["acting"].upn == "pat@example.test"
    assert resolver.asked == [USER_OID]


# ------------------------------------------------------ the delegated path never asks


def test_a_cowork_caller_never_reaches_graph(tmp_path, fake_api, resolver):
    gw = on(tmp_path, fake_api)
    assert gw.client.post(CALL, json=ARGS, headers=user_headers()).status_code == 200
    session, _ = open_session(gw, user_headers())
    assert call(gw, session, "client_situation", {"client_id": 2001}).status_code == 200
    assert resolver.asked == []
    assert {e.user_display_name for e in gw.events()} == {"Pat Writer"}


# ---------------------------------------------------------------------- fail-soft


@pytest.mark.parametrize("fake", [FakeResolver(None), FakeResolver(error=RuntimeError("graph is down"))], ids=["no-answer", "raises"])
def test_a_lookup_that_fails_never_stops_the_request(tmp_path, fake_api, fake):
    channel_wiring.set_display_name_resolver(fake)
    try:
        gw = on(tmp_path, fake_api)
        reply = gw.client.post(CALL, json=ARGS, headers=placeholder_headers())
    finally:
        channel_wiring.set_display_name_resolver(None)
    assert reply.status_code == 200
    assert {e.user_display_name for e in gw.events()} == {PLACEHOLDER_NAME}


def test_a_resolver_that_raises_is_logged_with_the_oid_and_the_error_type_only(tmp_path, fake_api, caplog):
    channel_wiring.set_display_name_resolver(FakeResolver(error=RuntimeError("Pat Example pat@example.test")))
    try:
        gw = on(tmp_path, fake_api)
        with caplog.at_level(logging.DEBUG):
            gw.client.post(CALL, json=ARGS, headers=placeholder_headers())
    finally:
        channel_wiring.set_display_name_resolver(None)
    assert USER_OID in caplog.text and "RuntimeError" in caplog.text
    assert "Pat Example" not in caplog.text and "pat@example.test" not in caplog.text


# ----------------------------------------------------- over a fake Graph, end to end


def test_two_requests_for_one_person_cost_one_graph_call_and_no_name_is_logged_or_summarised(tmp_path, fake_api, caplog):
    seen: list[httpx.Request] = []

    def graph(request):
        seen.append(request)
        return httpx.Response(200, json={"displayName": "Pat Example", "userPrincipalName": "pat@example.test"})

    channel_wiring.set_display_name_resolver(GraphDisplayNameResolver(
        token_provider=lambda: "graph-token", client=httpx.Client(transport=httpx.MockTransport(graph))))
    try:
        gw = on(tmp_path, fake_api)
        with caplog.at_level(logging.DEBUG):
            for _ in range(2):
                assert gw.client.post(CALL, json=ARGS, headers=placeholder_headers()).status_code == 200
    finally:
        channel_wiring.set_display_name_resolver(None)
    assert len(seen) == 1 and seen[0].url.path.endswith(f"/users/{USER_OID}")
    assert fake_api.calls[1]["acting"].upn == "pat@example.test"
    assert "Pat Example" not in caplog.text and "pat@example.test" not in caplog.text
    for event in gw.events():
        assert "Pat Example" not in (event.request_summary or "") and "pat@example.test" not in (event.request_summary or "")
        assert "Pat Example" not in (event.error or "")


def test_graph_refusing_the_role_leaves_the_request_working_with_the_placeholder(tmp_path, fake_api):
    channel_wiring.set_display_name_resolver(GraphDisplayNameResolver(
        token_provider=lambda: "graph-token",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": {"code": "Forbidden"}})))))
    try:
        gw = on(tmp_path, fake_api)
        assert gw.client.post(CALL, json=ARGS, headers=placeholder_headers()).status_code == 200
    finally:
        channel_wiring.set_display_name_resolver(None)
    assert {e.user_display_name for e in gw.events()} == {PLACEHOLDER_NAME}
