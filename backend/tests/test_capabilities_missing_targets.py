"""A prepare against a target that does not exist is a typed refusal, never a 500. [CH-14]

Found live: `claim_transition_prepare` for a client-programme-year with no claim cell answered 500
`internal_error`, while `claim_cell_history` for the same cell answered a typed error. A reader cannot tell a
crash from "there is nothing there" if both are 500, and the orchestrator would say it "failed unexpectedly"
for something that is simply not recorded. Every write capability is driven here at a target that is not in
the book, over the API endpoint and through the gateway.
"""
from __future__ import annotations

import pytest

from application import wiring
from tests.test_capabilities_api import agent_headers, post
from tests.test_agent_principal import api, entra  # noqa: F401 - fixtures
from tests.test_channel_writes import world  # noqa: F401 - fixture

GONE = 999999
CELL = {"client_id": GONE, "program_code": "GA_JTC", "tax_year": 2023}

#: (tool, arguments at a target nobody has recorded, status, code)
MISSING = [
    ("claim_transition_prepare", {**CELL, "status": "proposed"}, 404, "claim_not_found"),
    ("finding_resolve_prepare", {"client_id": GONE, "tax_year": 2023, "finding_id": "nope", "resolution": "accept"}, None, None),
    ("finding_reopen_prepare", {"client_id": GONE, "finding_id": "nope"}, None, None),
    ("claim_record_prepare", {**CELL, "status": "assessed"}, None, None),
    ("engagement_set_prepare", {"client_id": GONE, "program_code": "GA_JTC", "scope": "in_scope"}, None, None),
    ("base_year_set_prepare", {"client_id": GONE, "program_code": "GA_JTC", "base_tax_year": 2020}, None, None),
    ("claim_package_create_prepare", {"client_id": GONE, "tax_year": 2023}, None, None),
]


@pytest.fixture(autouse=True)
def no_run_for_any_client():
    """The package preview reads the latest run; a client nobody calculated has none."""
    wiring.set_claim_package_source(type("NoRuns", (), {"latest_run": staticmethod(lambda client_id: None)})())
    yield
    wiring.set_claim_package_source(None)


@pytest.mark.parametrize("tool,args,status,code", MISSING, ids=[m[0] for m in MISSING])
def test_a_prepare_at_a_missing_target_is_never_a_500(entra, api, world, tool, args, status, code):  # noqa: F811
    response = post(api, tool, args, agent_headers())
    assert response.status_code < 500, f"{tool}: {response.status_code} {response.text}"
    body = response.json()
    if response.status_code != 200:
        assert body["error"]["code"] != "internal_error" and body["error"]["retryable"] is False
    if status:
        assert response.status_code == status and body["error"]["code"] == code
        assert "No claim recorded for client" in body["error"]["message"]
