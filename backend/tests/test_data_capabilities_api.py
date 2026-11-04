"""The data tools over HTTP: `POST /api/capabilities/{tool}` for a person and for the gateway. [CH-16d]

The route is generic, so these tests pin what the data tools need from it: the client in a query is
authorized by the same entitlement as every other tool (a model cannot reach another client by writing
its id), a refusal arrives as a stable body with its field and its wait, and Copilot Cowork is refused
employee-level rows before anything reads them. No route was added, so the route inventory is unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bootstrap import wiring
from application.capabilities import catalog
from application.capabilities.data_catalog import data_catalog
from bootstrap.channel_wiring import set_writer_entitlement
from application.data.executor import Rows
from bootstrap.data_wiring import set_data_query_service
from application.identity import AllowListAuthorizer
from application.rate_limit import RateLimiter
from tests.data_caps_fixture import Writers, person
from tests.test_agent_principal import OTHER_OID, acting_header, api, entra  # noqa: F401 - fixtures
from tests.test_auth import OID
from tests.test_capabilities_api import agent_headers, post, user_headers
from tests.test_data_query_service import ScriptedExecutor, scripted_service

AGGREGATE = {"dataset": "unit_year_master", "client_id": 1001, "select": ["worksite_id"],
             "measures": [{"column": "*", "agg": "count", "as": "n"}]}
EMPLOYEES = {"dataset": "employee_eligibility", "client_id": 1001, "select": ["record_token"], "limit": 2}


@pytest.fixture
def served(entra, api):  # noqa: F811
    executor = ScriptedExecutor(rows=Rows(("method", "worksite_id", "n"), (("min_max", "site-a", 2), ("pay_period", "site-b", 2))))
    set_data_query_service(scripted_service(executor))
    set_writer_entitlement(Writers())
    yield executor
    set_data_query_service(None)
    set_writer_entitlement(None)


@pytest.mark.parametrize("headers", [user_headers, agent_headers], ids=["person", "gateway-for-a-person"])
def test_a_query_over_http_returns_the_envelope(served, api, headers):
    response = post(api, "data_query", AGGREGATE, headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool"] == "data_query"
    assert body["facts"]["rows"] == [{"method": "min_max", "worksite_id": "site-a", "n": 2}, {"method": "pay_period", "worksite_id": "site-b", "n": 2}]
    assert body["provenance"]["source"] == "Source: warehouse tcc_gold.unit_year_master" and "user_only_facts" not in body
    assert served.calls and served.calls[0]["client_id"] == 1001


def test_the_catalog_over_http_is_the_direct_call(served, api):
    body = post(api, "data_catalog", {"dataset": "unit_month_summary"}).json()
    # a person's own token is not first-party, so the catalog tells them what the direct call tells such a caller
    assert body["facts"] == data_catalog(person(channel=None), dataset="unit_month_summary").to_dict()["facts"]


def test_a_client_the_caller_may_not_see_is_refused_before_any_query_runs(served, api):
    wiring.set_client_authorizer(AllowListAuthorizer({}))
    for tool, args in (("data_query", AGGREGATE),
                       ("data_distinct_values", {"client_id": 1001, "dataset": "unit_month_summary", "column": "worksite_id"})):
        response = post(api, tool, args)
        assert response.status_code == 403 and response.json()["error"]["code"] == "client_not_authorized", tool
    assert served.calls == [], "nothing reached the data source"


def test_naming_another_client_in_the_query_is_authorized_on_that_client(served, api):
    wiring.set_client_authorizer(AllowListAuthorizer({OID: {1001}}))
    assert post(api, "data_query", AGGREGATE).status_code == 200
    other = post(api, "data_query", {**AGGREGATE, "client_id": 2002})
    assert other.status_code == 403 and served.calls[-1]["client_id"] == 1001


def test_a_refusal_has_a_stable_body_with_its_field(served, api):
    response = post(api, "data_query", {**AGGREGATE, "select": ["nope"]})
    error = response.json()["error"]
    assert response.status_code == 422 and error["code"] == "unknown_column" and error["field"] == "select" and error["retryable"] is False


def test_a_schema_violation_is_the_invokers_422(served, api):
    response = post(api, "data_query", {**AGGREGATE, "limit": 9999})
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_arguments"


def test_the_budget_refusal_is_a_429_that_says_when_to_retry(entra, api):  # noqa: F811
    rows = Rows(("method", "worksite_id", "n"), (("min_max", "site-a", 2),))
    set_data_query_service(scripted_service(ScriptedExecutor(rows=rows), budget=RateLimiter(1)))
    set_writer_entitlement(Writers())
    try:
        assert post(api, "data_query", AGGREGATE).status_code == 200
        response = post(api, "data_query", AGGREGATE)
    finally:
        set_data_query_service(None)
        set_writer_entitlement(None)
    assert response.status_code == 429 and response.json()["error"]["retryable"] is True
    assert response.json()["error"]["retry_after_seconds"] >= 1


def test_cowork_is_refused_employee_rows_before_the_source_is_read(served, api):
    reader = agent_headers(channel="cowork", oid=OTHER_OID)
    response = post(api, "data_query", EMPLOYEES, reader)
    assert response.status_code == 403 and response.json()["error"]["code"] == "employee_level_not_available"
    assert served.calls == []


def test_a_cowork_writer_is_served_the_persons_lane(served, api):
    from tests.data_caps_fixture import WRITER_OID

    response = post(api, "data_query", EMPLOYEES, agent_headers(channel="cowork", oid=WRITER_OID))
    assert response.status_code == 200 and response.json()["user_only_facts"] == ["rows"]


def test_the_three_tools_are_listed_by_the_catalog_endpoint_and_no_route_was_added(served, api):
    tools = {t["name"]: t for t in api.get("/api/capabilities", headers=user_headers()).json()["tools"]}
    assert all(name in tools and tools[name]["kind"] == "read" for name in ("data_catalog", "data_query", "data_distinct_values"))
    assert tools["data_query"]["sensitive"] is True and tools["data_query"]["schema"] == catalog.get("data_query").schema
    inventory = json.loads((Path(__file__).parent / "route_inventory.json").read_text(encoding="utf-8"))
    assert not [r for r in inventory if "data_query" in r or "data_catalog" in r]
