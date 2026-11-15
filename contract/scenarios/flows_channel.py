"""Stage C5 scenarios: the channel gateway (REST and MCP), generated from `inventory/channel.json` so every tool is covered."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHANNEL = json.loads((ROOT / "contract" / "inventory" / "channel.json").read_text(encoding="utf-8"))
TENANT = "00000000-0000-0000-0000-0000000000aa"
READER, WRITER = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000a2"
GATEWAY_AUD = "api://contract-gateway"
APP_ID = "00000000-0000-0000-0000-0000000000c1"

TOKENS = {
    "user": {"kind": "user", "oid": READER, "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": [], "claims": {"azp": APP_ID}},
    "writer_user": {"kind": "user", "oid": WRITER, "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": [], "claims": {"azp": APP_ID}},
    "agent": {"kind": "agent", "aud": GATEWAY_AUD, "roles": ["Channel.Invoke"], "claims": {"azp": APP_ID}},
    "agent_no_role": {"kind": "agent", "aud": GATEWAY_AUD, "roles": [], "claims": {"azp": APP_ID}},
    "agent_with_scope": {"kind": "agent", "aud": GATEWAY_AUD, "roles": ["Channel.Invoke"], "claims": {"scp": "Channel.Access"}},
    "expired": {"kind": "user", "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": [], "exp_in": -7200},
    "forged": {"kind": "user", "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": [], "key": "other"},
    "wrong_audience": {"kind": "user", "aud": "api://not-the-gateway", "scp": "Channel.Access", "roles": []},
    "no_scope": {"kind": "user", "aud": GATEWAY_AUD, "scp": "openid", "roles": []},
    "mixed": {"kind": "user", "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": ["Channel.Invoke"]},
    "other_tenant_user": {"kind": "user", "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": [], "tid": "00000000-0000-0000-0000-0000000000ff"},
    "no_oid": {"kind": "user", "aud": GATEWAY_AUD, "scp": "Channel.Access", "roles": [], "drop": ["oid"]},
}


def bearer(name: str) -> dict[str, str]:
    return {"authorization": f"Bearer {{{{token.{name}}}}}"}


def acting(oid: str = READER, **over: str) -> dict[str, str]:
    h = {"x-acting-user-oid": oid, "x-acting-user-name": "Acting Person", "x-acting-tenant": TENANT, "x-channel": "teams", "x-conversation-id": "conv-1", "x-correlation-id": "corr-1"}
    h.update({k.replace("_", "-"): v for k, v in over.items()})
    return h


def agent_headers(oid: str = READER, **over: str) -> dict[str, str]:
    return {**bearer("agent"), **acting(oid, **over)}


BY_NAME = {
    "client_id": 1001, "tax_year": 2025, "program_code": "GA_JTC", "state": "GA", "method": "min_max", "worksite_id": "GA_ATL_HQ", "unit_id": "GA_ATL_HQ",
    "finding_id": "policy:test_of_twos:ALL:2025", "resolution": "accept", "status": "proposed", "scope": "in_scope", "base_year": 2024, "limit": 3, "year": 2025,
    "action": "add_headcount", "magnitude": 2, "name": "Cascade", "query": "Cascade", "text": "Cascade",
}


def sample(spec: dict[str, Any], name: str = "") -> Any:
    if "enum" in spec:
        return BY_NAME.get(name) if BY_NAME.get(name) in spec["enum"] else spec["enum"][0]
    if "anyOf" in spec:
        return sample(spec["anyOf"][0], name)
    kind = spec.get("type")
    if name in BY_NAME and kind in ("integer", "string", "number"):
        return BY_NAME[name]
    if kind == "object":
        return {k: sample(v, k) for k, v in (spec.get("properties") or {}).items() if k in (spec.get("required") or [])}
    if kind == "array":
        return [sample(spec.get("items") or {}, name)]
    return {"integer": 1, "number": 1, "string": "x", "boolean": False}.get(kind, "x")


def typical(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool["schema"]
    return {k: sample(v, k) for k, v in (schema.get("properties") or {}).items() if k in (schema.get("required") or [])}


def invalid(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool["schema"]
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    base = typical(tool)
    if required:
        first = required[0]
        kind = props[first].get("type")
        base[first] = {"integer": "abc", "string": {"nested": 1}, "number": "abc", "boolean": "maybe", "array": "abc", "object": "abc"}.get(kind, None)
        return base
    return {"zz_unknown_argument": 1}


def build_all(b: Any) -> list[dict[str, Any]]:
    S, C, write = b.S, b.C, b.write
    tools = CHANNEL["tools"]
    names = [t["name"] for t in tools]
    made = []

    # ----------------------------------------------------------------------------------------- REST
    rest: list[dict[str, Any]] = [
        S("health", "GET", "/channel/health"), S("ready", "GET", "/channel/ready"), S("tools.no-token", "GET", "/channel/v1/tools"),
        S("tools.delegated", "GET", "/channel/v1/tools", headers=bearer("user")),
        S("tools.agent", "GET", "/channel/v1/tools", headers=agent_headers()),
        S("tools.agent-no-acting-headers", "GET", "/channel/v1/tools", headers=bearer("agent")),
        S("unknown-route", "GET", "/channel/v1/nope"), S("docs-not-served", "GET", "/docs"), S("openapi-not-served", "GET", "/openapi.json"),
        S("tools.wrong-method", "POST", "/channel/v1/tools", json={}),
    ]
    for name, spec in TOKENS.items():
        rest.append(S(f"auth.{name}", "GET", "/channel/v1/tools", headers=bearer(name) if not name.startswith("agent") else {**bearer(name), **acting()}))
    for sid, hdr in [("no-tenant", {k: v for k, v in acting().items() if k != "x-acting-tenant"}), ("wrong-tenant", acting(**{"x_acting_tenant": "00000000-0000-0000-0000-0000000000ff"})),
                     ("bad-channel", acting(x_channel="fax")), ("no-channel", {k: v for k, v in acting().items() if k != "x-channel"}),
                     ("bad-oid", acting("nope")), ("no-name", {k: v for k, v in acting().items() if k != "x-acting-user-name"}),
                     ("no-conversation", {k: v for k, v in acting().items() if k != "x-conversation-id"}), ("bad-correlation", acting(x_correlation_id="bad id!")),
                     ("long-name", acting(x_acting_user_name="n" * 300)), ("cowork-channel-asserted-by-agent", acting(x_channel="cowork"))]:
        rest.append(S(f"acting.{sid}", "GET", "/channel/v1/tools", headers={**bearer("agent"), **hdr}))
    for t in tools:
        n = t["name"]
        rest.append(S(f"tool.{n}.typical", "POST", f"/channel/v1/tools/{n}", json={"args": typical(t)}, headers=agent_headers(WRITER, x_correlation_id=f"c-{n}")))
        rest.append(S(f"tool.{n}.invalid", "POST", f"/channel/v1/tools/{n}", json={"args": invalid(t)}, headers=agent_headers(WRITER, x_correlation_id=f"i-{n}")))
    rest += [
        S("tool.unknown", "POST", "/channel/v1/tools/no_such_tool", json={"args": {}}, headers=agent_headers()),
        S("tool.no-token", "POST", "/channel/v1/tools/book_rank", json={"args": {}}),
        S("tool.delegated-book-rank", "POST", "/channel/v1/tools/book_rank", json={"args": {}}, headers=bearer("user")),
        S("tool.body-not-json", "POST", "/channel/v1/tools/book_rank", body_text="{nope", headers={**agent_headers(), "content-type": "application/json"}),
        S("tool.body-args-not-object", "POST", "/channel/v1/tools/book_rank", json={"args": [1]}, headers=agent_headers()),
        S("tool.body-empty", "POST", "/channel/v1/tools/book_rank", headers=agent_headers()),
        S("tool.body-extra-fields", "POST", "/channel/v1/tools/book_rank", json={"args": {}, "zz": 1}, headers=agent_headers()),
        S("tool.body-too-large", "POST", "/channel/v1/tools/book_rank", json={"args": {"pad": "x" * 70000}}, headers=agent_headers()),
        S("tool.idempotency-key-too-long", "POST", "/channel/v1/tools/book_rank", json={"args": {}, "idempotency_key": "k" * 201}, headers=agent_headers()),
        S("tool.ping-off", "POST", "/channel/v1/tools/channel_ping", json={"args": {}}, headers=agent_headers()),
        # the numeric-integrity guard (ADR-008): facts come from tool results; a draft figure that is not one is refused
        S("guard.read-facts", "POST", "/channel/v1/tools/book_rank", json={"args": {}}, headers=agent_headers(READER, x_conversation_id="guard-1", x_correlation_id="g-1")),
        S("guard.verify-matching", "POST", "/channel/v1/tools/verify_figures", json={"args": {"draft": "1 of 1 clients have been assessed."}}, headers=agent_headers(READER, x_conversation_id="guard-1", x_correlation_id="g-2")),
        S("guard.verify-mismatching", "POST", "/channel/v1/tools/verify_figures", json={"args": {"draft": "Identified credit is $123,456 across 77 clients."}}, headers=agent_headers(READER, x_conversation_id="guard-1", x_correlation_id="g-3")),
        S("guard.verify-other-conversation", "POST", "/channel/v1/tools/verify_figures", json={"args": {"draft": "1 of 1 clients have been assessed."}}, headers=agent_headers(READER, x_conversation_id="guard-2", x_correlation_id="g-4")),
        S("guard.verify-no-draft", "POST", "/channel/v1/tools/verify_figures", json={"args": {}}, headers=agent_headers(READER, x_conversation_id="guard-1", x_correlation_id="g-5")),
        # narration audit (orchestrator only)
        S("narration.no-token", "POST", "/channel/v1/audit/narration", json={}),
        S("narration.delegated", "POST", "/channel/v1/audit/narration", json={}, headers=bearer("user")),
        S("narration.agent-empty", "POST", "/channel/v1/audit/narration", json={}, headers=agent_headers()),
        S("narration.agent-bad", "POST", "/channel/v1/audit/narration", body_text="x", headers={**agent_headers(), "content-type": "application/json"}),
        # downloads
        S("download.unknown-ticket", "GET", "/channel/v1/downloads/not-a-ticket"),
        S("download.unknown-ticket-with-token", "GET", "/channel/v1/downloads/not-a-ticket", headers=bearer("user")),
        S("download.bad-token", "GET", "/channel/v1/downloads/not-a-ticket", headers={"authorization": "Bearer garbage"}),
    ]
    # the two-step write: prepare, then commit with the token, replayed, with the wrong tool, with changed arguments
    f = {"client_id": 1001, "tax_year": 2025, "finding_id": "policy:test_of_twos:ALL:2025", "resolution": "accept", "note": "contract"}
    h = lambda cid: agent_headers(WRITER, x_correlation_id=cid)  # noqa: E731
    rest += [
        S("write.prepare", "POST", "/channel/v1/tools/finding_resolve_prepare", json={"args": f}, headers=h("w-1"), capture={"token": "body.result.confirmation_token"}),
        S("write.prepare-as-reader", "POST", "/channel/v1/tools/finding_resolve_prepare", json={"args": f}, headers=agent_headers(READER, x_correlation_id="w-2")),
        S("write.commit-wrong-tool", "POST", "/channel/v1/tools/finding_reopen_commit", json={"args": {"client_id": 1001, "finding_id": f["finding_id"]}, "confirmation_token": "{{token}}"}, headers=h("w-3")),
        S("write.commit-changed-args", "POST", "/channel/v1/tools/finding_resolve_commit", json={"args": {**f, "resolution": "drop"}, "confirmation_token": "{{token}}"}, headers=h("w-4")),
        S("write.commit-other-user", "POST", "/channel/v1/tools/finding_resolve_commit", json={"args": f, "confirmation_token": "{{token}}"}, headers=agent_headers(READER, x_correlation_id="w-5")),
        S("write.commit", "POST", "/channel/v1/tools/finding_resolve_commit", json={"args": f, "confirmation_token": "{{token}}"}, headers=h("w-6"), capture={"ref": "body.result.confirmation_ref"}),
        S("write.commit-replayed", "POST", "/channel/v1/tools/finding_resolve_commit", json={"args": f, "confirmation_token": "{{token}}"}, headers=h("w-7")),
        S("write.commit-no-token", "POST", "/channel/v1/tools/finding_resolve_commit", json={"args": f}, headers=h("w-8")),
        S("write.commit-garbage-token", "POST", "/channel/v1/tools/finding_resolve_commit", json={"args": f, "confirmation_token": "garbage"}, headers=h("w-9")),
        S("write.findings-after", "POST", "/channel/v1/tools/findings_list", json={"args": {"client_id": 1001, "tax_year": 2025}}, headers=h("w-10")),
        S("write.claim-package-prepare", "POST", "/channel/v1/tools/claim_package_create_prepare", json={"args": {"client_id": 1001, "tax_year": 2025}}, headers=h("w-11"), capture={"ptoken": "body.result.confirmation_token"}),
        S("write.claim-package-commit", "POST", "/channel/v1/tools/claim_package_create_commit", json={"args": {"client_id": 1001, "tax_year": 2025}, "confirmation_token": "{{ptoken}}"}, headers=h("w-12")),
        S("write.claim-package-link", "POST", "/channel/v1/tools/claim_package_link", json={"args": {"client_id": 1001, "tax_year": 2025}}, headers=h("w-13"), capture={"url": "body.result.download_url"}),
    ]
    # rate limit: 6 a minute per caller, frozen clock
    for i in range(1, 9):
        rest.append(S(f"ratelimit.{i}", "POST", "/channel/v1/tools/book_rank", json={"args": {}}, headers=agent_headers(READER, x_conversation_id="rl", x_correlation_id=f"rl-{i}") | {"x-acting-user-oid": "00000000-0000-0000-0000-0000000000d1"}))
    made.append(write("g1_rest", "G1", rest))

    # ----------------------------------------------------------------------------------------- MCP
    H = {**bearer("user"), "content-type": "application/json", "accept": "application/json, text/event-stream"}
    HS = {**H, "mcp-session-id": "{{sid}}", "mcp-protocol-version": "2025-06-18"}
    rpc = lambda i, method, params=None: {"jsonrpc": "2.0", "id": i, "method": method, **({"params": params} if params is not None else {})}  # noqa: E731
    mcp: list[dict[str, Any]] = [
        S("no-token", "POST", "/mcp", json=rpc(1, "initialize", {})), S("garbage-token", "POST", "/mcp", json=rpc(1, "initialize", {}), headers={"authorization": "Bearer x"}),
        S("initialize", "POST", "/mcp", json=rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "contract", "version": "1"}}), headers=H, capture={"sid": "header.mcp-session-id"}),
        S("initialize-old-version", "POST", "/mcp", json=rpc(2, "initialize", {"protocolVersion": "2024-01-01"}), headers=H),
        S("initialize-no-params", "POST", "/mcp", json=rpc(3, "initialize"), headers=H),
        S("initialized-notification", "POST", "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=HS),
        S("ping", "POST", "/mcp", json=rpc(4, "ping"), headers=HS), S("tools-list", "POST", "/mcp", json=rpc(5, "tools/list"), headers=HS),
        S("tools-list-no-session", "POST", "/mcp", json=rpc(5, "tools/list"), headers={**H, "mcp-protocol-version": "2025-06-18"}),
        S("tools-list-unknown-session", "POST", "/mcp", json=rpc(5, "tools/list"), headers={**H, "mcp-session-id": "nope"}),
        S("tools-list-bad-protocol-version", "POST", "/mcp", json=rpc(5, "tools/list"), headers={**HS, "mcp-protocol-version": "1999-01-01"}),
        S("tools-list-bad-origin", "POST", "/mcp", json=rpc(5, "tools/list"), headers={**HS, "origin": "https://evil.example"}),
        S("unknown-method", "POST", "/mcp", json=rpc(6, "no/such"), headers=HS), S("null-id", "POST", "/mcp", json={"jsonrpc": "2.0", "id": None, "method": "ping"}, headers=HS),
        S("bool-id", "POST", "/mcp", json={"jsonrpc": "2.0", "id": True, "method": "ping"}, headers=HS),
        S("not-jsonrpc", "POST", "/mcp", json={"hello": 1}, headers=HS), S("batch-array", "POST", "/mcp", json=[rpc(7, "ping")], headers=HS),
        S("not-json", "POST", "/mcp", body_text="{nope", headers=HS), S("empty-body", "POST", "/mcp", headers=HS),
        S("client-response-ignored", "POST", "/mcp", json={"jsonrpc": "2.0", "id": 9, "result": {}}, headers=HS),
        S("tools-call-missing-name", "POST", "/mcp", json=rpc(10, "tools/call", {}), headers=HS),
        S("tools-call-unknown-tool", "POST", "/mcp", json=rpc(11, "tools/call", {"name": "no_such_tool", "arguments": {}}), headers=HS),
        S("tools-call-arguments-not-object", "POST", "/mcp", json=rpc(12, "tools/call", {"name": "book_rank", "arguments": [1]}), headers=HS),
        S("get-405", "GET", "/mcp", headers=bearer("user")), S("get-no-token", "GET", "/mcp"),
    ]
    for i, t in enumerate(tools):
        mcp.append(S(f"call.{t['name']}.typical", "POST", "/mcp", json=rpc(100 + i * 2, "tools/call", {"name": t["name"], "arguments": typical(t)}), headers=HS))
        mcp.append(S(f"call.{t['name']}.invalid", "POST", "/mcp", json=rpc(101 + i * 2, "tools/call", {"name": t["name"], "arguments": invalid(t)}), headers=HS))
    mcp += [
        S("other-user-session", "POST", "/mcp", json=rpc(300, "tools/list"), headers={**HS, **bearer("writer_user")}),
        S("delete-other-user", "DELETE", "/mcp", headers={**HS, **bearer("writer_user")}), S("delete", "DELETE", "/mcp", headers=HS),
        S("after-delete", "POST", "/mcp", json=rpc(301, "tools/list"), headers=HS), S("delete-again", "DELETE", "/mcp", headers=HS),
        S("agent-initialize", "POST", "/mcp", json=rpc(1, "initialize", {"protocolVersion": "2025-06-18"}), headers={**bearer("agent"), **acting(), "content-type": "application/json"}),
    ]
    made.append(write("g1_mcp", "G1", mcp, tokens=TOKENS))
    # tokens are needed in the REST scenario too
    scenario = json.loads((b.HERE / "g1_rest.json").read_text(encoding="utf-8"))
    scenario["tokens"] = TOKENS
    (b.HERE / "g1_rest.json").write_text(json.dumps(scenario, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return made
