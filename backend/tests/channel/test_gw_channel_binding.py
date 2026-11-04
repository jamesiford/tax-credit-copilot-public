"""Which channel a trusted caller may claim, and the gateway's fail-closed lane guard. [RM-02]

An agent's `X-Channel` is an assertion by a trusted service. A real channel name is not enough: with a
registry configured (`CHANNEL_CALLER_CHANNELS`) the claim must be one THAT app is registered for, so a
second registered caller cannot pose as Teams to be handed employee rows. And the gateway's copy of the
lane rule is positive: only a first-party channel is trusted, so an unknown one is refused like Cowork.
"""
from __future__ import annotations

import pytest

from application.capabilities.lanes import EMPLOYEE_LEVEL_CODE
from application.identity import ActingUser
from channel.auth import Caller
from channel.config import GatewayConfigurationError, load_settings
from channel.lane_guard import blocks_employee_level
from gateway_harness import (
    ORCHESTRATOR_APP, OTHER_OID, agent_headers, agent_token, build_gateway, user_headers, user_token,
)
from test_gw_config import ENV
from test_gw_data_lanes import SECRET_TOKEN, employee_rows, mcp_call

TOOLS = "/channel/v1/tools"
OTHER_APP = "77777777-6666-4555-8444-333333333333"
THIRD_APP = "55555555-4444-4333-8222-111111111111"


def error(response) -> str:
    return response.json()["error"]["code"]


def authenticate(gateway, headers):
    return gateway.services.authenticator.authenticate({k.lower(): v for k, v in headers.items()})


# ------------------------------------------------------------------- the setting


def test_the_binding_is_read_from_the_environment_and_normalised():
    s = load_settings({**ENV, "CHANNEL_CALLER_CHANNELS": f"{ORCHESTRATOR_APP.upper()}=teams|m365-copilot, {OTHER_APP}=teams"})
    assert s.caller_channels == {ORCHESTRATOR_APP: ("teams", "m365-copilot"), OTHER_APP: ("teams",)}
    assert load_settings(ENV).caller_channels == {}


@pytest.mark.parametrize("value", [
    f"{ORCHESTRATOR_APP}=cowork", f"{ORCHESTRATOR_APP}=api-test", f"{ORCHESTRATOR_APP}=teams|cowork",
    "not-a-guid=teams", f"{ORCHESTRATOR_APP}=", ORCHESTRATOR_APP, f"{ORCHESTRATOR_APP}=carrier-pigeon",
], ids=["cowork", "api-test", "mixed", "bad-app", "no-channel", "no-equals", "unknown"])
def test_a_binding_that_could_let_an_agent_claim_a_non_first_party_channel_refuses_to_start(value):
    with pytest.raises(GatewayConfigurationError, match="CHANNEL_CALLER_CHANNELS"):
        load_settings({**ENV, "CHANNEL_CALLER_CHANNELS": value})


# ------------------------------------------------------------- the claim is bound


def bound(tmp_path, fake_api, **channels):
    return build_gateway(tmp_path, api=fake_api, caller_channels=channels,
                         allowed_caller_app_ids=(OTHER_APP, ORCHESTRATOR_APP))


def test_a_caller_may_claim_the_channels_it_is_registered_for(tmp_path, fake_api):
    gw = bound(tmp_path, fake_api, **{ORCHESTRATOR_APP: ("teams", "m365-copilot")})
    for channel in ("teams", "m365-copilot"):
        assert authenticate(gw, agent_headers(channel=channel)).acting.channel == channel
        assert gw.client.get(TOOLS, headers=agent_headers(channel=channel)).status_code == 200


def test_a_caller_cannot_claim_a_real_channel_it_is_not_registered_for(tmp_path, fake_api):
    gw = bound(tmp_path, fake_api, **{ORCHESTRATOR_APP: ("teams",)})
    response = gw.client.get(TOOLS, headers=agent_headers(channel="m365-copilot"))
    assert response.status_code == 403 and error(response) == "channel_not_allowed"


def test_a_second_registered_caller_cannot_pose_as_the_orchestrator_s_channel(tmp_path, fake_api):
    """The spoof: another app is allowed to call (it is on the allow-list) and claims `teams` to be handed rows."""
    gw = bound(tmp_path, fake_api, **{ORCHESTRATOR_APP: ("teams",), OTHER_APP: ("m365-copilot",)})
    spoof = agent_headers(agent_token(app_id=OTHER_APP, roles=None), channel="teams")
    response = gw.client.get(TOOLS, headers=spoof)
    assert response.status_code == 403 and error(response) == "channel_not_allowed"
    honest = agent_headers(agent_token(app_id=OTHER_APP, roles=None), channel="m365-copilot")
    assert gw.client.get(TOOLS, headers=honest).status_code == 200


def test_with_a_registry_an_app_it_does_not_list_asserts_nothing_even_with_the_role(tmp_path, fake_api):
    gw = bound(tmp_path, fake_api, **{ORCHESTRATOR_APP: ("teams",)})
    unlisted = agent_headers(agent_token(app_id=THIRD_APP), channel="teams")  # holds the role, is not in the registry
    response = gw.client.get(TOOLS, headers=unlisted)
    assert response.status_code == 403 and error(response) == "channel_not_allowed"


def test_a_token_with_no_app_id_asserts_nothing_once_a_registry_exists(tmp_path, fake_api):
    gw = bound(tmp_path, fake_api, **{ORCHESTRATOR_APP: ("teams",)})
    anonymous_app = agent_headers(agent_token(app_id=None), channel="teams")
    assert gw.client.get(TOOLS, headers=anonymous_app).status_code == 403


def test_without_a_registry_a_registered_caller_keeps_enum_level_trust(gateway):
    for channel in ("teams", "m365-copilot"):
        assert gateway.client.get(TOOLS, headers=agent_headers(channel=channel)).status_code == 200


def test_the_startup_says_when_no_registry_is_configured(tmp_path, fake_api, caplog):
    import logging

    from channel.app import create_app
    from gateway_harness import settings

    api = build_gateway(tmp_path, api=fake_api).services.api
    with caplog.at_level(logging.WARNING, logger="tcc.channel"):
        caplog.clear()
        create_app(settings(), api=api)
    assert any("CHANNEL_CALLER_CHANNELS is not set" in r.getMessage() for r in caplog.records)
    with caplog.at_level(logging.WARNING, logger="tcc.channel"):
        caplog.clear()
        create_app(settings(caller_channels={ORCHESTRATOR_APP: ("teams",)}), api=api)
    assert not any("CHANNEL_CALLER_CHANNELS" in r.getMessage() for r in caplog.records)


# ----------------------------------------------- the claims no registry can allow


@pytest.mark.parametrize("channel", ["cowork", "api-test", "carrier-pigeon", "Teams", ""])
def test_an_agent_can_never_claim_a_channel_that_is_not_first_party(tmp_path, fake_api, channel):
    gw = bound(tmp_path, fake_api, **{ORCHESTRATOR_APP: ("teams",)})
    assert gw.client.get(TOOLS, headers=agent_headers(channel=channel)).status_code in (400, 403)


def test_an_agent_that_names_no_channel_is_refused(gateway):
    assert gateway.client.get(TOOLS, headers=agent_headers(channel=None)).status_code == 400


def test_a_persons_token_is_always_cowork_whatever_headers_it_carries(gateway):
    headers = user_headers(**{"X-Channel": "teams", "X-Acting-User-Oid": OTHER_OID})
    caller = authenticate(gateway, headers)
    assert (caller.kind, caller.acting.channel, caller.acting.assurance) == ("delegated", "cowork", "delegated")
    assert not caller.acting.is_first_party


# --------------------------------------------------------- the gateway's lane guard


def caller_for(**acting) -> Caller:
    return Caller(ActingUser(oid=OTHER_OID, **acting), "agent", "role")


async def never_a_writer(_oid: str) -> bool:
    return False


async def always_a_writer(_oid: str) -> bool:
    return True


LANE = {"user_only_facts": ["rows"], "blocks": []}


@pytest.mark.anyio
@pytest.mark.parametrize("acting, blocked", [
    ({"channel": "teams"}, False),
    ({"channel": "m365-copilot"}, False),
    ({"channel": "cowork", "assurance": "delegated"}, True),
    ({"channel": "api-test"}, True),
    ({"channel": None}, True),
    ({"channel": "carrier-pigeon"}, True),
    ({"channel": "teams", "assurance": "delegated"}, True),
], ids=["teams", "m365-copilot", "cowork", "api-test", "no-channel", "unknown", "delegated-teams"])
async def test_the_lane_guard_trusts_only_a_first_party_channel(acting, blocked):
    assert await blocks_employee_level(caller_for(**acting), LANE, never_a_writer) is blocked


@pytest.mark.anyio
async def test_a_writer_is_never_blocked_and_a_result_with_no_person_lane_is_never_blocked():
    assert not await blocks_employee_level(caller_for(channel="cowork"), LANE, always_a_writer)
    assert not await blocks_employee_level(caller_for(channel="cowork"), {"facts": {}}, never_a_writer)


def test_the_gateway_refuses_rows_for_a_channel_it_does_not_trust_even_when_the_api_forwards_them(tmp_path, fake_api):
    """The API's check is the first wall; if a result still arrives carrying a person lane, the gateway's is the second."""
    gw = build_gateway(tmp_path, api=fake_api)
    fake_api.replies["data_query"] = (200, employee_rows())
    result = mcp_call(gw, user_headers(user_token(oid=OTHER_OID)))
    assert result["isError"] is True and result["structuredContent"]["error"]["code"] == EMPLOYEE_LEVEL_CODE
    assert SECRET_TOKEN not in str(result)
