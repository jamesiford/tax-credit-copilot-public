"""Who the gateway lets in, and as whom. [CH-06]

The two accepted shapes, and every way to be refused. The properties worth proving are
the ones that stop a caller acquiring somebody else's rights: an agent cannot name a
user from another tenant or skip the acting-user headers; a person cannot name anyone
but themselves; no token, no role, no scope means no entry; and the stable error body
never carries a token.
"""
from __future__ import annotations

import pytest

from gateway_harness import (
    ORCHESTRATOR_APP, OTHER_TENANT, USER_OID, OTHER_OID, agent_headers, agent_token, user_headers, user_token, build_gateway,
)

TOOLS = "/channel/v1/tools"


def error(response):
    body = response.json()["error"]
    assert set(body) >= {"code", "message", "retryable"} and body["retryable"] is False
    return body["code"]


# ------------------------------------------------------------------ accepted


def test_an_agent_with_the_role_is_let_in_and_the_path_is_the_role(gateway):
    assert gateway.client.get(TOOLS, headers=agent_headers()).status_code == 200
    caller = gateway.services.authenticator.authenticate(
        {k.lower(): v for k, v in agent_headers().items()})
    assert (caller.kind, caller.authorised_by, caller.app_id) == ("agent", "role", ORCHESTRATOR_APP)
    assert caller.acting.assurance == "channel-asserted" and caller.acting.oid == USER_OID


def test_an_agent_on_the_allow_list_is_let_in_without_the_role(tmp_path, fake_api):
    gw = build_gateway(tmp_path, api=fake_api, allowed_caller_app_ids=(ORCHESTRATOR_APP,))
    headers = agent_headers(agent_token(roles=None))
    assert gw.client.get(TOOLS, headers=headers).status_code == 200
    caller = gw.services.authenticator.authenticate({k.lower(): v for k, v in headers.items()})
    assert caller.authorised_by == "allow-list"


def test_a_delegated_user_is_let_in_as_themselves(gateway):
    assert gateway.client.get(TOOLS, headers=user_headers()).status_code == 200
    caller = gateway.services.authenticator.authenticate(
        {k.lower(): v for k, v in user_headers().items()}, conversation_id="mcp-session-1")
    assert (caller.kind, caller.authorised_by) == ("delegated", "scope")
    acting = caller.acting
    assert (acting.oid, acting.channel, acting.assurance) == (USER_OID, "cowork", "delegated")
    assert acting.upn == "pat@example.com" and acting.conversation_id == "mcp-session-1"


def test_a_delegated_user_cannot_name_somebody_else_by_header(gateway):
    headers = user_headers(**{"X-Acting-User-Oid": OTHER_OID, "X-Acting-User-Name": "Somebody Else", "X-Channel": "teams"})
    caller = gateway.services.authenticator.authenticate({k.lower(): v for k, v in headers.items()})
    assert caller.acting.oid == USER_OID and caller.acting.display_name == "Pat Writer" and caller.acting.channel == "cowork"


def test_health_and_ready_need_no_token(gateway):
    assert gateway.client.get("/channel/health").json() == {"status": "ok"}
    assert gateway.client.get("/channel/ready").json()["ready"] is True


# ------------------------------------------------------------------- refused


def test_no_token_is_a_401_that_asks_for_one(gateway):
    response = gateway.client.get(TOOLS)
    assert response.status_code == 401 and error(response) == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["not-a-jwt", agent_token(aud="api://someone-else")], ids=["garbage", "wrong-audience"])
def test_a_token_that_proves_nothing_is_a_401(gateway, token):
    response = gateway.client.get(TOOLS, headers=agent_headers(token))
    assert response.status_code == 401 and error(response) == "unauthenticated"
    assert token not in response.text


def test_a_token_from_another_tenant_is_a_401(gateway):
    wrong = agent_token(iss=f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0")
    assert gateway.client.get(TOOLS, headers=agent_headers(wrong)).status_code == 401


def test_an_app_without_the_role_and_not_on_the_list_is_a_403(gateway):
    response = gateway.client.get(TOOLS, headers=agent_headers(agent_token(roles=None)))
    assert response.status_code == 403 and error(response) == "caller_not_allowed"


def test_an_app_on_neither_path_is_a_403_even_with_other_roles(gateway):
    assert gateway.client.get(TOOLS, headers=agent_headers(agent_token(roles=("Something.Else",)))).status_code == 403


def test_an_app_only_token_with_a_scope_is_a_403(gateway):
    response = gateway.client.get(TOOLS, headers=agent_headers(agent_token(scp="Channel.Access")))
    assert response.status_code == 403 and error(response) == "mixed_token"


def test_a_delegated_token_without_the_scope_is_a_403(gateway):
    response = gateway.client.get(TOOLS, headers=user_headers(user_token(scp="user_impersonation")))
    assert response.status_code == 403 and error(response) == "missing_scope"


def test_a_delegated_token_carrying_the_agent_role_is_a_403(gateway):
    response = gateway.client.get(TOOLS, headers=user_headers(user_token(roles=["Channel.Invoke"])))
    assert response.status_code == 403 and error(response) == "mixed_token"


def test_a_delegated_token_for_another_tenant_is_refused(gateway):
    assert gateway.client.get(TOOLS, headers=user_headers(user_token(tid=OTHER_TENANT))).status_code == 403


# ---------------------------------------------------- the acting-user headers


@pytest.mark.parametrize(
    "drop", ["oid", "name", "tenant", "channel", "conversation"],
)
def test_an_agent_must_name_the_user_on_every_request(gateway, drop):
    response = gateway.client.get(TOOLS, headers=agent_headers(**{drop: None}))
    assert response.status_code in (400, 403) and error(response) in {"invalid_acting_user", "tenant_mismatch"}


@pytest.mark.parametrize(
    "overrides",
    [{"oid": "not-a-guid"}, {"tenant": "nope"}, {"channel": "carrier-pigeon"}, {"channel": "cowork"},
     {"name": "x" * 300}, {"conversation": "c" * 300}],
    ids=["bad-oid", "bad-tenant", "bad-channel", "agent-cannot-claim-cowork", "long-name", "long-conversation"],
)
def test_malformed_acting_headers_are_refused(gateway, overrides):
    assert gateway.client.get(TOOLS, headers=agent_headers(**overrides)).status_code in (400, 403)


def test_an_acting_user_from_another_tenant_is_a_403(gateway):
    response = gateway.client.get(TOOLS, headers=agent_headers(tenant=OTHER_TENANT))
    assert response.status_code == 403 and error(response) == "tenant_mismatch"


def test_the_correlation_id_is_kept_when_given_and_made_when_not(gateway):
    given = gateway.services.authenticator.authenticate({k.lower(): v for k, v in agent_headers().items()})
    assert given.acting.correlation_id == "corr-1"
    made = gateway.services.authenticator.authenticate(
        {k.lower(): v for k, v in agent_headers(correlation=None).items()})
    assert made.acting.correlation_id and made.acting.correlation_id != "corr-1"


def test_a_malformed_correlation_id_is_refused(gateway):
    response = gateway.client.get(TOOLS, headers=agent_headers(correlation="not valid!"))
    assert response.status_code == 400 and error(response) == "invalid_correlation_id"


def test_the_gateway_never_echoes_a_token_in_an_error(gateway):
    token = agent_token(roles=None)
    response = gateway.client.get(TOOLS, headers=agent_headers(token))
    assert token not in response.text and "Bearer" not in response.text
