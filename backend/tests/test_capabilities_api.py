"""`GET /api/capabilities` and `POST /api/capabilities/{tool}`. [CH-06a]

The endpoint must add nothing and lose nothing: every tool's `facts` over HTTP are
the direct capability call's, byte for byte, for a signed-in person and for the
gateway acting for one. Around that: the schema is enforced, each way to fail has a
stable status and error body, a write is refused for somebody who may not write
whatever the caller claims, and a slow call is told so rather than left hanging.
"""
from __future__ import annotations

import io
import json
import time
from datetime import timedelta

import pytest
from openpyxl import load_workbook

from application import wiring
from application.capabilities import catalog, registry
from application.identity import AllowListAuthorizer
from domain.channel import utcnow
from tests.test_agent_principal import (
    AGENT_OID, OTHER_OID, USER_OID, acting_header, api, entra, mint, mint_app,  # noqa: F401 - fixtures
)
from tests.test_artifacts_api import FakeSource, service  # noqa: F401 - fixture
from tests.test_channel_writes import ENGAGE, world  # noqa: F401 - fixture
from test_capabilities_equivalence import _DrillReader, _KNOWN_TOKEN, _seed, book, claims_repo, findings_repo, gold  # noqa: F401,E501
from test_simulate_unit import SITE, cascade, wired  # noqa: F401


def user_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {mint()}"}


def agent_headers(**acting) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_app()}", "X-TCC-Acting-User": acting_header(**acting)}


CALLERS = pytest.mark.parametrize(
    "headers", [user_headers, agent_headers], ids=["person", "gateway-for-a-person"],
)

READS = [
    ("book_rank", {}),
    ("client_resolve", {"name_or_text": "Cascade"}),
    ("client_situation", {"client_id": 2001}),
    ("claim_cell_history", {"client_id": 2001, "program_code": "GA_JTC", "tax_year": 2023}),
    ("client_trend", {"client_id": 2001}),
    ("client_at_risk", {"client_id": 2001, "tax_year": 2023, "state": "GA", "method": "min_max"}),
    ("client_eligibility", {"client_id": 2001, "tax_year": 2023, "state": "GA", "method": "pay_period"}),
    ("client_discovery", {"client_id": 2001, "state": "GA"}),
]


@pytest.fixture
def reads_world(request, book, claims_repo, gold):  # noqa: F811
    """Claims are seeded over HTTP while the API is still open; only then is it locked to tokens."""
    _seed(claims_repo)
    request.getfixturevalue("entra")


def post(api, tool, args=None, headers=None, **body):
    return api.post(f"/api/capabilities/{tool}", json={"args": args or {}, **body}, headers=headers or user_headers())


# ------------------------------------------------------------------- catalog


def test_the_catalog_endpoint_lists_every_tool_but_the_plumbing(entra, api):
    tools = api.get("/api/capabilities", headers=user_headers()).json()["tools"]
    names = {t["name"] for t in tools}
    assert names == {s.name for s in catalog.CATALOG} - {"claim_package_redeem"}
    assert all({"name", "kind", "schema", "implemented", "description"} <= set(t) for t in tools)
    assert all(t["implemented"] for t in tools)


def test_the_catalog_needs_a_token(entra, api):
    assert api.get("/api/capabilities").status_code == 401


# ------------------------------------------------------- facts equal the call


@CALLERS
@pytest.mark.parametrize("tool, args", READS, ids=[t for t, _ in READS])
def test_the_facts_over_http_are_the_direct_calls(reads_world, api, headers, tool, args):
    response = post(api, tool, args, headers())
    assert response.status_code == 200, response.text
    direct = registry.call(tool, **args).to_dict()
    body = response.json()
    assert body["facts"] == direct["facts"]
    assert body["provenance"] == direct["provenance"] and body["blocks"] == direct["blocks"]
    assert body["tool"] == tool and body["disclaimer"]


def test_findings_and_the_employee_drill_over_http(entra, api, findings_repo):  # noqa: F811
    from application.capabilities.findings import findings_list

    over_http = post(api, "findings_list", {"client_id": 1001, "tax_year": 2025, "state": "GA"}).json()
    assert over_http["facts"] == findings_list(1001, 2025, "GA").to_dict()["facts"]

    wiring.set_gold_reader(_DrillReader())
    try:
        drill = post(api, "employee_drill", {
            "client_id": 1001, "record_token": _KNOWN_TOKEN, "tax_year": 2025, "state": "GA"})
        assert drill.status_code == 200 and drill.json()["tool"] == "employee_drill"
    finally:
        wiring.set_gold_reader(None)


def test_simulate_over_http_is_the_direct_call(entra, api, wired):  # noqa: F811
    args = {"client_id": 2001, "tax_year": 2025, "worksite_id": SITE, "action": "add_headcount", "magnitude": 2}
    body = post(api, "simulate", args).json()
    assert body["facts"] == registry.call("simulate", **args).to_dict()["facts"]


# ---------------------------------------------------------------- the failures


@pytest.mark.parametrize(
    "tool, args, status, code",
    [
        ("client_situation", {"client_id": "abc"}, 422, "invalid_arguments"),
        ("client_situation", {}, 422, "invalid_arguments"),
        ("client_situation", {"client_id": 2001, "surprise": 1}, 422, "invalid_arguments"),
        ("client_eligibility", {"client_id": 2001, "tax_year": 1800}, 422, "invalid_arguments"),
        ("simulate", {"client_id": 2001, "tax_year": 2025, "worksite_id": "x", "action": "bribe"}, 422, "invalid_arguments"),
        ("no_such_tool", {}, 404, "unknown_tool"),
        ("verify_figures", {"draft_text": "x"}, 501, "gateway_local"),
    ],
)
def test_each_failure_has_a_status_and_a_stable_body(entra, api, tool, args, status, code):
    response = post(api, tool, args)
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["message"] and error["retryable"] is False
    assert set(error) == {"code", "message", "retryable"}


def test_a_client_nobody_calculated_is_a_409_and_an_unauthored_year_a_422(entra, api, gold):  # noqa: F811
    assert post(api, "claim_cell_history", {"client_id": 2001, "program_code": "GA_JTC", "tax_year": 2023}
                ).json()["error"]["code"] == "not_calculated"
    declined = post(api, "client_at_risk", {"client_id": 2001, "tax_year": 1999})
    assert declined.status_code == 422 and declined.json()["error"]["code"] == "year_not_authored"


def test_a_client_the_caller_may_not_see_is_refused_before_the_tool_runs(entra, api, book, claims_repo):  # noqa: F811
    wiring.set_client_authorizer(AllowListAuthorizer({}))
    response = post(api, "client_situation", {"client_id": 2001})
    assert response.status_code == 403 and response.json()["error"]["code"] == "not_authorized"


def test_a_commit_naming_a_client_is_authorized_on_the_client_inside_it(entra, api, world):  # noqa: F811
    wiring.set_client_authorizer(AllowListAuthorizer({}))
    body = {"confirmation_token": "x" * 20, "idempotency_key": "k", "arguments": ENGAGE}
    assert post(api, "engagement_set_commit", body, agent_headers()).status_code == 403


def test_a_slow_tool_is_told_so_rather_than_left_hanging(entra, api, monkeypatch):
    monkeypatch.setenv("CAPABILITY_TIMEOUT_SECONDS", "1")
    monkeypatch.setitem(registry.FUNCTIONS, "book_rank", lambda limit=8: time.sleep(1.3))
    response = post(api, "book_rank")
    assert response.status_code == 504
    assert response.json()["error"] == {"code": "timeout", "message": "book_rank did not finish in time", "retryable": True}


def test_a_bad_timeout_setting_is_refused_not_defaulted(monkeypatch):
    from application.capabilities.invoke import timeout_seconds

    monkeypatch.setenv("CAPABILITY_TIMEOUT_SECONDS", "soon")
    with pytest.raises(ValueError, match="CAPABILITY_TIMEOUT_SECONDS"):
        timeout_seconds()


def test_an_unexpected_failure_does_not_leak_its_text(entra, api, monkeypatch):
    def explode(limit=8):
        raise RuntimeError("password=hunter2 in the stack")

    monkeypatch.setitem(registry.FUNCTIONS, "book_rank", explode)
    response = post(api, "book_rank")
    assert response.status_code == 500 and "hunter2" not in response.text
    assert response.json()["error"]["code"] == "internal_error"


# ---------------------------------------------------------------- writes


def prepared(api, tool, args, headers):
    response = post(api, f"{tool}_prepare", args, headers)
    assert response.status_code == 200, response.text
    return response.json()["facts"]["confirmation"]["token"]


def commit(api, tool, args, headers, token, idem):
    """The commit call: the prepare's own arguments, with the token and the retry key beside them."""
    return post(api, f"{tool}_commit", args, headers, confirmation_token=token, idempotency_key=idem)


def test_a_write_over_http_is_two_steps_and_both_are_in_the_trail(entra, api, world):  # noqa: F811
    headers = agent_headers()
    token = prepared(api, "engagement_set", ENGAGE, headers)
    done = commit(api, "engagement_set", ENGAGE, headers, token, "k-1")
    assert done.status_code == 200 and done.json()["facts"]["replayed"] is False
    again = commit(api, "engagement_set", ENGAGE, headers, token, "k-1")
    assert again.json()["facts"]["replayed"] is True
    events = world.audit.for_user(USER_OID)
    assert {(e.tool_name, e.phase) for e in events} >= {
        ("engagement_set_prepare", "begin"), ("engagement_set_prepare", "end"),
        ("engagement_set_commit", "begin"), ("engagement_set_commit", "end"),
    }
    assert {e.identity_assurance for e in events} == {"channel-asserted"}


def test_the_writer_check_is_the_apis_whatever_the_caller_claims(entra, api, world):  # noqa: F811
    refused = post(api, "engagement_set_prepare", ENGAGE, agent_headers(oid=OTHER_OID))
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "not_authorized"
    assert not any(e.tool_name == "engagement_set_commit" for e in world.audit.for_user(OTHER_OID))


@pytest.mark.parametrize(
    "mutate, status, code",
    [
        (lambda a: {**a, "scope": "out_of_scope"}, 422, "confirmation_wrong_args"),
        (lambda a: a, 404, "confirmation_unknown"),
    ],
    ids=["tampered-arguments", "unknown-token"],
)
def test_a_commit_that_does_not_match_its_preview_is_refused(entra, api, world, mutate, status, code):  # noqa: F811
    headers = agent_headers()
    token = prepared(api, "engagement_set", ENGAGE, headers)
    token = token if code == "confirmation_wrong_args" else "z" * 43
    refused = commit(api, "engagement_set", mutate(ENGAGE), headers, token, "k")
    assert refused.status_code == status and refused.json()["error"]["code"] == code


def test_a_commit_that_names_its_token_twice_must_agree(entra, api, world):  # noqa: F811
    body = {"confirmation_token": "a" * 20, "idempotency_key": "k", "arguments": ENGAGE}
    response = commit(api, "engagement_set", body, agent_headers(), "b" * 20, "k")
    assert response.status_code == 422 and "differ" in response.json()["error"]["message"]


# --------------------------------------------------------- the claim package


PACKAGE = {"client_id": 1001, "tax_year": 2024}


def test_the_package_is_built_on_commit_and_is_a_valid_workbook(entra, api, world, service):  # noqa: F811
    headers = agent_headers()
    preview = post(api, "claim_package_create_prepare", PACKAGE, headers).json()
    assert preview["facts"]["preview"]["after"]["tax_year"] == 2024
    assert service.repository.live(1001, kind="claim_package") == [], "prepare builds nothing"
    token = preview["facts"]["confirmation"]["token"]

    done = commit(api, "claim_package_create", PACKAGE, headers, token, "pk-1")
    assert done.status_code == 200, done.text
    result = done.json()["facts"]["result"]
    assert result["download_path"] == f"/api/clients/1001/artifacts/{result['artifact_id']}"
    assert len(result["sha256"]) == 64 and result["file_name"].endswith(".xlsx") and "sas" not in json.dumps(result).lower()

    served = api.get(result["download_path"], headers=headers)
    assert served.status_code == 200 and served.headers["x-content-sha256"] == result["sha256"]
    assert load_workbook(io.BytesIO(served.content)).sheetnames[0] == "Coverage"
    assert {(e.tool_name, e.phase) for e in world.audit.for_user(USER_OID)} >= {
        ("claim_package_create_prepare", "begin"), ("claim_package_create_commit", "end")}


def test_the_package_of_a_client_with_no_run_is_a_409_at_prepare(entra, api, world, service):  # noqa: F811
    wiring.set_claim_package_source(FakeSource(run=None))
    refused = post(api, "claim_package_create_prepare", PACKAGE, agent_headers())
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_calculated"


def build_package(api, headers):
    token = prepared(api, "claim_package_create", PACKAGE, headers)
    done = commit(api, "claim_package_create", PACKAGE, headers, token, "pk")
    return done.json()["facts"]["result"]


def test_a_link_before_any_package_exists_says_so(entra, api, world, service):  # noqa: F811
    response = post(api, "claim_package_link", PACKAGE, agent_headers())
    assert response.status_code == 409 and "claim_package_create" in response.json()["error"]["message"]


def test_a_link_is_single_use_user_bound_and_expires(entra, api, world, service, monkeypatch):  # noqa: F811
    headers = agent_headers()
    built = build_package(api, headers)
    link = post(api, "claim_package_link", PACKAGE, headers).json()["facts"]
    assert link["single_use"] is True and link["ticket_minutes"] == 15 and "storage" not in link["download_path"]
    ticket = link["download_path"].rsplit("/", 1)[1]
    assert link["sha256"] == built["sha256"]

    wrong = post(api, "claim_package_redeem", {"ticket": ticket, "expected_user_oid": OTHER_OID}, headers)
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] == "confirmation_wrong_user"
    spent = post(api, "claim_package_redeem", {"ticket": ticket, "expected_user_oid": USER_OID}, headers)
    assert spent.status_code == 200
    assert spent.json()["facts"]["artifact_id"] == built["artifact_id"] and spent.json()["facts"]["user_oid"] == USER_OID
    again = post(api, "claim_package_redeem", {"ticket": ticket}, headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "confirmation_replayed"

    late = post(api, "claim_package_link", PACKAGE, headers).json()["facts"]["download_path"].rsplit("/", 1)[1]
    import application.capabilities.package as package

    monkeypatch.setattr(package, "utcnow", lambda: utcnow() + timedelta(minutes=16))
    expired = post(api, "claim_package_redeem", {"ticket": late}, headers)
    assert expired.status_code == 409 and expired.json()["error"]["code"] == "confirmation_expired"
    unknown = post(api, "claim_package_redeem", {"ticket": "q" * 40}, headers)
    assert unknown.status_code == 404


def test_the_gateway_only_tool_is_registered_but_answered_elsewhere():
    assert "verify_figures" in registry.FUNCTIONS and catalog.GATEWAY_LOCAL in catalog.get("verify_figures").tags
    result = registry.call("verify_figures", draft_text="The credit is 4,231 dollars.")
    assert result.facts["status"] == "rejected" and result.facts["violations"][0]["token"]
