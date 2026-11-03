"""Through the gateway, a change to a claim nobody recorded is a typed 404, not a 500. [CH-14]

The API test (`test_capabilities_missing_targets.py`) pins the endpoint; this pins that the gateway passes the
typed refusal on, audits it as a refusal to find, and that the orchestrator's reader never sees "failed
unexpectedly" for something that is simply not there.
"""
from __future__ import annotations

import httpx
import pytest

from application import wiring
from gateway_harness import USER_OID, agent_headers, build_gateway
from tests.test_agent_principal import entra, mint_app  # noqa: F401 - fixtures
from tests.test_artifacts_api import service  # noqa: F401 - fixture
from tests.test_channel_writes import world  # noqa: F401 - fixture

import main

MISSING = {"client_id": 999999, "program_code": "GA_JTC", "tax_year": 2023, "status": "proposed"}


@pytest.fixture
def stack(tmp_path, entra, world, service):  # noqa: F811
    gw = build_gateway(tmp_path, transport=httpx.ASGITransport(app=main.app), token_provider=mint_app, writers={USER_OID})
    gw.services.pipeline._entitlement = world.writers
    gw.audit = world.audit
    return gw


def test_a_transition_with_nothing_to_move_is_a_404_the_reader_can_act_on(stack):
    response = stack.client.post("/channel/v1/tools/claim_transition_prepare", json={"args": MISSING}, headers=agent_headers())
    assert response.status_code == 404, response.text
    error = response.json()["error"]
    assert error["code"] == "claim_not_found" and error["retryable"] is False
    assert "No claim recorded for client 999999, GA_JTC, TY2023" in error["message"]


def test_nothing_was_written_and_the_trail_says_what_happened(stack, world):
    stack.client.post("/channel/v1/tools/claim_transition_prepare", json={"args": MISSING}, headers=agent_headers())
    assert wiring.get_claim_repository().current(999999, "GA_JTC", 2023) is None
    events = sorted(world.audit.for_user(USER_OID), key=lambda e: e.event_seq)
    assert [(e.tool_name, e.phase) for e in events] == [("claim_transition_prepare", "begin"), ("claim_transition_prepare", "end")]
    assert events[-1].outcome == "error" and "internal_error" not in (events[-1].error or "")
