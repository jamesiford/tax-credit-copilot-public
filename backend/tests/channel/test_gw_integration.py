"""The gateway in front of the REAL API. [CH-06]

Everything above uses a fake API. This runs the gateway against `main.app` itself
(entra on, fake keys, SQLite stores) so what the gateway sends is judged by the API's
own guard: the app-only token and the acting-user header, the writer check, the
confirmation token, and the audit written by the capability. It is where "exactly one
begin/end pair for a write" and "a ticket works once, for one person" are proved rather
than assumed.
"""
from __future__ import annotations

import io
import json
from datetime import timedelta

import httpx
import pytest
from openpyxl import load_workbook

from application import wiring
from domain.channel import utcnow
from gateway_harness import OTHER_OID, USER_OID, agent_headers, build_gateway, user_headers, user_token
from tests.test_agent_principal import entra, mint_app  # noqa: F401 - fixtures
from tests.test_channel_writes import world  # noqa: F401 - fixture
from tests.test_artifacts_api import RUN, FakeSource, service  # noqa: F401 - fixture
from tests.test_capabilities_equivalence import gold  # noqa: F401 - fixture

PACKAGE = {"client_id": 1001, "tax_year": 2024}
ENGAGE = {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope", "note": "signed"}


@pytest.fixture
def stack(tmp_path, entra, world, service):  # noqa: F811
    """The gateway wired to the real API, with the writer allow-list shared by both."""
    import main

    gw = build_gateway(tmp_path, transport=httpx.ASGITransport(app=main.app), token_provider=mint_app, writers={USER_OID})
    gw.services.pipeline._entitlement = world.writers
    gw.audit = world.audit
    return gw


def post(gw, tool, args, headers=None, **body):
    return gw.client.post(f"/channel/v1/tools/{tool}", json={"args": args, **body}, headers=headers or agent_headers())


def commit(gw, tool, args, token, idem, headers=None):
    """The commit call: the prepare's own arguments, with the token and the retry key beside them."""
    return post(gw, f"{tool}_commit", args, headers, confirmation_token=token, idempotency_key=idem)


def two_steps(gw, tool, args, headers=None, idem="idem-1"):
    prepared = post(gw, f"{tool}_prepare", args, headers)
    assert prepared.status_code == 200, prepared.text
    token = prepared.json()["facts"]["confirmation"]["token"]
    return prepared, commit(gw, tool, args, token, idem, headers)


def shape(events):
    return sorted({(e.tool_name, e.phase, e.outcome) for e in events})


# ------------------------------------------------------------------------ reads


def test_a_read_through_the_real_api_has_the_apis_facts_and_is_then_verifiable(stack, gold):  # noqa: F811
    from application.capabilities import registry

    body = post(stack, "client_trend", {"client_id": 2001}).json()
    assert body["facts"] == registry.call("client_trend", client_id=2001).to_dict()["facts"]
    figure = str(body["facts"]["years"][1]["annual_average"])
    verified = post(stack, "verify_figures", {"draft_text": f"The average was {figure}."}).json()["facts"]
    assert verified["status"] == "pass"
    assert post(stack, "verify_figures", {"draft_text": f"The average was {figure}1."}).json()["facts"]["status"] == "rejected"


def test_a_person_with_a_delegated_token_reads_too(stack, gold):  # noqa: F811
    response = stack.client.post("/channel/v1/tools/client_trend", json={"args": {"client_id": 2001}}, headers=user_headers())
    assert response.status_code == 200
    assert {e.identity_assurance for e in stack.events()} == {"delegated"}


# ----------------------------------------------------------------------- writes


def test_a_write_has_exactly_one_begin_end_pair_per_step_all_in_one_correlation(stack):
    prepared, committed = two_steps(stack, "engagement_set", ENGAGE)
    assert committed.status_code == 200 and committed.json()["facts"]["replayed"] is False
    events = stack.events()
    assert shape(events) == [("engagement_set_commit", "begin", "pending"), ("engagement_set_commit", "end", "ok"),
                             ("engagement_set_prepare", "begin", "pending"), ("engagement_set_prepare", "end", "ok")]
    assert len(events) == 4
    assert {e.correlation_id for e in events if e.tool_name.endswith("_commit")} == {"corr-1"}
    assert {e.identity_assurance for e in events} == {"channel-asserted"}


def test_a_replayed_commit_is_a_replay_not_a_second_write(stack):
    prepared, committed = two_steps(stack, "engagement_set", ENGAGE)
    token = prepared.json()["facts"]["confirmation"]["token"]
    again = commit(stack, "engagement_set", ENGAGE, token, "idem-1")
    assert again.json()["facts"]["replayed"] is True
    commits = [e for e in stack.audit.for_user(USER_OID) if e.tool_name == "engagement_set_commit" and e.phase == "end"]
    assert [e.outcome for e in commits] == ["ok", "ok"], "one end event per attempt; the write itself happened once"


def test_the_apis_writer_check_refuses_even_when_the_gateway_would_let_it_through(stack):
    stack.services.pipeline._entitlement = type("Everyone", (), {"is_writer": staticmethod(lambda oid: True)})()
    headers = agent_headers(oid=OTHER_OID)
    prepared = post(stack, "engagement_set_prepare", ENGAGE, headers)
    assert prepared.status_code == 403 and prepared.json()["error"]["code"] == "not_authorized"
    events = stack.audit.for_user(OTHER_OID)
    assert shape(events) == [("engagement_set_prepare", "begin", "pending"), ("engagement_set_prepare", "end", "refused")]


def test_a_commit_for_a_person_the_gateway_does_not_know_is_refused_without_a_call(stack):
    stack.services.pipeline._entitlement = type("Nobody", (), {"is_writer": staticmethod(lambda oid: False)})()
    refused = commit(stack, "engagement_set", ENGAGE, "x" * 30, "i")
    assert refused.status_code == 403
    assert [(e.phase, e.outcome) for e in stack.audit.for_user(USER_OID)] == [("single", "refused")]


# ------------------------------------------------------------------ the package


def build_package(gw, headers=None):
    _, committed = two_steps(gw, "claim_package_create", PACKAGE, headers, idem="pkg-1")
    assert committed.status_code == 200, committed.text
    return committed.json()["facts"]["result"]


def link(gw, headers=None):
    response = post(gw, "claim_package_link", PACKAGE, headers)
    assert response.status_code == 200, response.text
    return response.json()["facts"]["download_path"]


def test_the_package_reaches_a_browser_by_ticket_alone_once(stack):
    built = build_package(stack)
    path = link(stack)
    assert path.startswith("/channel/v1/downloads/")
    first = stack.client.get(path)
    assert first.status_code == 200 and first.headers["x-content-sha256"] == built["sha256"]
    assert load_workbook(io.BytesIO(first.content)).sheetnames[0] == "Coverage"
    assert first.headers["cache-control"] == "no-store"
    second = stack.client.get(path)
    assert second.status_code == 410 and second.json()["error"]["code"] == "confirmation_replayed"


def test_nothing_the_gateway_says_contains_a_storage_address_or_sas(stack):
    build_package(stack)
    path = link(stack)
    text = json.dumps(stack.client.post("/channel/v1/tools/claim_package_link", json={"args": PACKAGE}, headers=agent_headers()).json())
    assert not any(marker in text.lower() for marker in ("sig=", "sv=", "blob.core", "sas", "sharedaccess"))
    assert path.startswith("/channel/v1/downloads/")


def test_the_download_is_audited_as_the_person_the_ticket_was_minted_for(stack):
    build_package(stack)
    stack.client.get(link(stack))
    events = sorted((e for e in stack.audit.for_user(USER_OID) if e.tool_name == "claim_package_download"),
                    key=lambda e: e.event_seq)
    assert [(e.phase, e.outcome, e.action_kind) for e in events] == [("begin", "pending", "read"), ("end", "ok", "read")]
    assert events[0].client_id == 1001 and events[0].channel == "teams" and events[0].conversation_id == "conv-1"
    assert [a.outcome for a in wiring.get_artifact_service().repository.accesses(1001)] == ["served"]


def test_a_ticket_is_bound_to_its_person_and_a_wrong_person_does_not_burn_it(stack):
    build_package(stack)
    path = link(stack)
    stranger = user_headers(user_token(oid=OTHER_OID))
    refused = stack.client.get(path, headers=stranger)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "confirmation_wrong_user"
    owner = stack.client.get(path, headers=user_headers())
    assert owner.status_code == 200, "the owner's link survived the stranger's attempt"


def test_a_ticket_expires(stack, monkeypatch):
    build_package(stack)
    path = link(stack)
    import application.capabilities.package as package

    monkeypatch.setattr(package, "utcnow", lambda: utcnow() + timedelta(minutes=16))
    expired = stack.client.get(path)
    assert expired.status_code == 410 and expired.json()["error"]["code"] == "confirmation_expired"


def test_a_guess_is_a_404_and_a_bad_token_is_a_401(stack):
    assert stack.client.get("/channel/v1/downloads/" + "q" * 43).status_code == 404
    assert stack.client.get("/channel/v1/downloads/x", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_downloads_are_rate_limited_per_address(tmp_path, entra, world, service):  # noqa: F811
    import main

    gw = build_gateway(tmp_path, transport=httpx.ASGITransport(app=main.app), token_provider=mint_app, rate_limit_per_minute=3)
    statuses = [gw.client.get("/channel/v1/downloads/" + "q" * 43).status_code for _ in range(5)]
    assert statuses[:3] == [404, 404, 404] and statuses[3:] == [429, 429]


def test_a_link_before_the_package_exists_is_the_apis_409(stack):
    response = post(stack, "claim_package_link", PACKAGE)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_calculated"
