"""One tool list: the catalog, MCP `tools/list`, the MAF tools, the gateway's REST list and the API's. [RM-13]

The catalog is the only place a tool is defined. Every surface is a generated view of it, and a view may differ from
the catalog only in ways the catalog itself declares: which tools a surface offers (tags and kinds), what a channel
that offers BOTH halves of a write says about it (`channel_description`), and what a MODEL is shown of the arguments
(`model_schema`, the reader's own arguments removed). This test states each of those differences out loud, as
literals, so a change to any of them is a visible edit here and not a quiet drift in an adapter:

    surface               offers                                   description               schema
    catalog (CATALOG)     everything, plumbing included            `description`             `schema`
    API REST list         built tools that are not plumbing        `description`             `schema`
    gateway REST list     the same, plus diagnostics when on       `description`             `schema`
    MCP tools/list        the same as the gateway's                `channel_description`     `schema`
    MAF FunctionTools     what a MODEL may name (see below)        `description`             `model_schema`
    portal chat           nine intents, each running one tool      (its own router prompt)   (none)

A model may not name: a commit (only the reader's `confirm` reaches it), the code-only tools (the client resolver and
the drill by opaque token, run by the orchestrator's own code), the gateway-local verifier and plumbing.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from parity_rig import PORTAL_OID, entra, mint  # noqa: F401 - fixtures (importing parity_rig also puts the gateway harness on the path)
from app.core.maf_catalog_tools import catalog_tool, catalog_tools
from application.capabilities import catalog
from application.capabilities.catalog_types import OWNED_CLIENT
from gateway_harness import FakeApi, build_gateway, user_headers
from parity_cases import CASES

#: Offered by nobody (plumbing the gateway's download route uses) and by a gateway only on request (a diagnostic).
PLUMBING = {"claim_package_redeem"}
DIAGNOSTICS = {"channel_ping"}
#: What a MODEL may not name, by name: the code runs these, a person confirms these, the gateway answers this.
CODE_ONLY = {"client_resolve", "employee_drill"}
GATEWAY_LOCAL = {"verify_figures"}
COMMITS = {s.name for s in catalog.CATALOG if s.kind == catalog.WRITE_COMMIT}
NOT_FOR_A_MODEL = CODE_ONLY | GATEWAY_LOCAL | COMMITS
PREPARES = {s.name for s in catalog.CATALOG if s.kind == catalog.WRITE_PREPARE}


def rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": id, "method": method, **({"params": params} if params is not None else {})}


def mcp_tools(gw) -> list[dict]:
    headers = user_headers()
    session = gw.client.post("/mcp", json=rpc("initialize", {"protocolVersion": "2025-06-18"}), headers=headers).headers["mcp-session-id"]
    return gw.client.post("/mcp", json=rpc("tools/list", id=2), headers={**headers, "Mcp-Session-Id": session}).json()["result"]["tools"]


@pytest.fixture
def gateways(tmp_path):
    """A gateway with diagnostics off and one with them on (`CHANNEL_DEBUG_WHOAMI`)."""
    (tmp_path / "on").mkdir()
    (tmp_path / "off").mkdir()
    return build_gateway(tmp_path / "off", api=FakeApi()), build_gateway(tmp_path / "on", api=FakeApi(), debug_whoami=True)


# ------------------------------------------------------------------------- what each surface offers


def test_the_catalogs_own_filters_are_exactly_the_declared_ones():
    names = {s.name for s in catalog.CATALOG}
    assert {s.name for s in catalog.CATALOG if catalog.INTERNAL in s.tags} == PLUMBING
    assert {s.name for s in catalog.offered()} == names - PLUMBING
    assert {s.name for s in catalog.offered_for_channel(debug=True)} == names - PLUMBING | DIAGNOSTICS
    assert {s.name for s in catalog.offered_for_channel()} == names - PLUMBING
    assert {s.name for s in catalog.model_offered()} == names - PLUMBING - NOT_FOR_A_MODEL
    assert {s.name for s in catalog.CATALOG if {catalog.CODE_ONLY, catalog.GATEWAY_LOCAL} & set(s.tags)} == CODE_ONLY | GATEWAY_LOCAL
    assert not [s.name for s in catalog.CATALOG if not s.implemented], "a declared-but-unbuilt tool would be listed by the API only"
    assert {s.name for s in catalog.offered_or_declared()} == names - PLUMBING


def test_the_gateways_rest_list_and_mcp_list_are_the_catalogs_offered_tools_in_its_order(gateways):
    for gw, debug in zip(gateways, (False, True)):
        expected = [s.name for s in catalog.offered_for_channel(debug=debug)]
        rest = gw.client.get("/channel/v1/tools", headers=user_headers()).json()["tools"]
        assert [t["name"] for t in rest] == expected
        assert [t["name"] for t in mcp_tools(gw)] == expected
        assert ("channel_ping" in expected) is debug


def test_the_api_list_is_the_catalog_less_plumbing(entra):  # noqa: F811
    import main

    tools = TestClient(main.app).get("/api/capabilities", headers={"Authorization": f"Bearer {mint()}"}).json()["tools"]
    assert [t["name"] for t in tools] == [s.name for s in catalog.offered_or_declared()]


def test_the_maf_tools_are_the_tools_a_model_may_name_sorted_by_name_and_no_commit_is_among_them():
    tools = catalog_tools()
    assert [t.name for t in tools] == sorted(s.name for s in catalog.model_offered())
    assert not {t.name for t in tools} & NOT_FOR_A_MODEL and {t.name for t in tools} >= PREPARES
    assert len(tools) == len(catalog.CATALOG) - len(PLUMBING) - len(NOT_FOR_A_MODEL)


# ------------------------------------------------------------------- words, schemas and hints


def test_every_surface_says_what_the_catalog_says_and_the_differences_are_the_declared_ones(gateways, entra):  # noqa: F811
    import main

    gw = gateways[1]
    mcp = {t["name"]: t for t in mcp_tools(gw)}
    rest = {t["name"]: t for t in gw.client.get("/channel/v1/tools", headers=user_headers()).json()["tools"]}
    api = {t["name"]: t for t in TestClient(main.app).get("/api/capabilities", headers={"Authorization": f"Bearer {mint()}"}).json()["tools"]}
    maf = {t.name: t for t in catalog_tools()}
    for spec in catalog.offered_for_channel(debug=True):
        for surface in (rest, mcp):
            assert surface[spec.name]["name"] == spec.name
        assert rest[spec.name]["description"] == spec.description and rest[spec.name]["schema"] == spec.schema
        assert rest[spec.name]["kind"] == spec.kind
        assert mcp[spec.name]["inputSchema"] == spec.schema
        assert mcp[spec.name]["description"] == catalog.channel_description(spec)
        assert mcp[spec.name]["annotations"] == catalog.behaviour_hints(spec)
        assert mcp[spec.name]["title"] == spec.name.replace("_", " ").capitalize()
        if spec.name in api:
            assert api[spec.name]["description"] == spec.description and api[spec.name]["schema"] == spec.schema
            assert api[spec.name]["kind"] == spec.kind
        if spec.name in maf:
            assert maf[spec.name].description == spec.description


def test_the_one_declared_wording_difference_is_the_write_sentence():
    for spec in catalog.CATALOG:
        extra = {catalog.WRITE_PREPARE: catalog.PREVIEW_SENTENCE, catalog.WRITE_COMMIT: catalog.COMMIT_SENTENCE}.get(spec.kind)
        expected = f"{spec.description} {extra}" if extra else spec.description
        assert catalog.channel_description(spec) == expected, spec.name


def test_a_model_is_shown_the_catalogs_schema_less_exactly_what_the_reader_owns():
    for spec in catalog.model_offered():
        shown = catalog_tool(spec).parameters()
        hidden = {o.name for o in spec.owned(OWNED_CLIENT)}
        owned = {o.name for o in spec.owned()}
        assert hidden <= {"client_id"}, "only the client is withheld from a model altogether"
        assert shown["properties"] == {k: v for k, v in spec.schema["properties"].items() if k not in hidden}, spec.name
        assert shown["required"] == [r for r in spec.schema.get("required", []) if r not in owned], spec.name
        assert shown["additionalProperties"] is True and spec.schema["additionalProperties"] is False
        assert shown["type"] == spec.schema["type"] == "object"
        assert catalog.model_schema(spec) == shown


def test_behaviour_hints_follow_the_kind_and_nothing_else():
    for spec in catalog.CATALOG:
        hints = catalog.behaviour_hints(spec)
        assert hints == {"readOnlyHint": spec.kind == catalog.READ, "destructiveHint": spec.kind == catalog.WRITE_COMMIT,
                         "idempotentHint": spec.kind == catalog.READ, "openWorldHint": False}


# ---------------------------------------------------------------------------------- the portal


def test_the_portals_intents_run_catalog_tools_and_the_parity_cases_name_real_ones():
    assert set(catalog.CHAT_INTENT_TOOL) == set(catalog.CAPABILITIES)
    assert set(catalog.CHAT_INTENT_TOOL.values()) <= {s.name for s in catalog.implemented()}
    assert {c.portal.intent for c in CASES if c.portal} <= set(catalog.CAPABILITIES)
    assert {c.tool for c in CASES} <= {s.name for s in catalog.model_offered()}
