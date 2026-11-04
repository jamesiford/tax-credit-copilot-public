"""The gateway in front of the REAL API and capability layer, for whole workflows. [CH-11]

Everything is real except what has no place to run offline: tokens are minted with a
throwaway key and checked against a fake JWKS, Gold is the equivalence suite's reader,
and the claim package's source rows are a fake that carries fields that must never reach
the file. The synthetic book, the claim repository, findings detection over the committed
synthetic payroll, the mediator, the confirmation store and the audit trail are the
production code on SQLite.

Two surfaces drive it the way the two kinds of caller do. `RestSurface` is the hosted
orchestrator's shape (an app-only token acting for a person, on Teams). `McpSurface` is
Cowork's (a person's own delegated token over JSON-RPC). A workflow test is written once
against `Surface` and runs on both.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from application import client_book
from application.composer.render import render_markdown
from channel.render import blocks_from, render_tool_text
from gateway_harness import OTHER_OID, USER_OID, Gateway, agent_headers, build_gateway, user_headers, user_token
from tests.test_agent_principal import entra, mint_app  # noqa: F401 - fixtures
from tests.test_artifacts_api import service  # noqa: F401 - fixture
from tests.test_capabilities_equivalence import BOOK, gold  # noqa: F401 - fixtures
from tests.test_channel_writes import world  # noqa: F401 - fixture

PAYROLL_CLIENT = 1001
PAYROLL_ROW = {"account_id": PAYROLL_CLIENT, "name": "Saltmarsh Kitchens", "industry": "Restaurants"}
UNASSESSED_ROW = {"account_id": 2004, "name": "Halloway Foods", "industry": "Food"}
SEEDS = ((2001, 2023, "140000"), (2002, 2024, "40495"), (2003, 2024, "12000"), (PAYROLL_CLIENT, 2024, "31500"))
THIRD_OID = "dddddddd-0000-4000-8000-0000000000d3"
MONEY = re.compile(r"\$[\d,]+(?:\.\d+)?")


@dataclass
class Reply:
    """One tool call's answer, the same shape whichever surface made it."""

    ok: bool
    body: dict[str, Any]
    text: str

    @property
    def facts(self) -> dict[str, Any]:
        return self.body.get("facts") or {}

    @property
    def error_code(self) -> str | None:
        return (self.body.get("error") or {}).get("code")

    @property
    def token(self) -> str:
        """The confirmation token a preview returned."""
        return self.facts["confirmation"]["token"]

    @property
    def confirmation_id(self) -> str:
        return self.facts["confirmation"]["confirmation_id"]


class Surface:
    """What a caller can do, independent of how it reaches the gateway."""

    channel: str
    assurance: str
    oid: str

    def call(self, tool: str, args: dict[str, Any] | None = None, **body: Any) -> Reply:
        raise NotImplementedError

    def commit(self, tool: str, args: dict[str, Any], token: str, idem: str) -> Reply:
        """`<tool>_commit` with the prepare's own arguments, the token and the retry key."""
        raise NotImplementedError

    def two_steps(self, tool: str, args: dict[str, Any], idem: str = "idem-1") -> tuple[Reply, Reply]:
        prepared = self.call(f"{tool}_prepare", args)
        assert prepared.ok, prepared.body
        return prepared, self.commit(tool, args, prepared.token, idem)

    def verify(self, text: str, *context: str) -> Reply:
        return self.call("verify_figures", {"draft_text": text, **({"allowed_context": list(context)} if context else {})})


class RestSurface(Surface):
    """The orchestrator's shape: an app-only token acting for `oid`, on Teams."""

    channel, assurance = "teams", "channel-asserted"

    def __init__(self, gw: Gateway, oid: str = USER_OID, conversation: str = "conv-rest") -> None:
        self.gw, self.oid, self.conversation = gw, oid, conversation

    def call(self, tool: str, args: dict[str, Any] | None = None, **body: Any) -> Reply:
        headers = agent_headers(oid=self.oid, conversation=self.conversation)
        response = self.gw.client.post(f"/channel/v1/tools/{tool}", json={"args": args or {}, **body}, headers=headers)
        payload = response.json()
        ok = response.status_code == 200
        return Reply(ok, payload, render_tool_text(payload) if ok else "")

    def commit(self, tool: str, args: dict[str, Any], token: str, idem: str) -> Reply:
        return self.call(f"{tool}_commit", args, confirmation_token=token, idempotency_key=idem)


class McpSurface(Surface):
    """Cowork's shape: the person's own delegated token, one MCP session per conversation."""

    channel, assurance = "cowork", "delegated"

    def __init__(self, gw: Gateway, oid: str = USER_OID) -> None:
        self.gw, self.oid, self._session, self._id = gw, oid, None, 0

    def _rpc(self, method: str, params: dict[str, Any]) -> httpx.Response:
        self._id += 1
        headers = user_headers(user_token(oid=self.oid))
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        return self.gw.client.post("/mcp", json={"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}, headers=headers)

    @property
    def session(self) -> str:
        if self._session is None:
            opened = self._rpc("initialize", {"protocolVersion": "2025-06-18"})
            assert opened.status_code == 200, opened.text
            self._session = opened.headers["mcp-session-id"]
        return self._session

    def call(self, tool: str, args: dict[str, Any] | None = None, **body: Any) -> Reply:
        assert self.session
        arguments = dict(args or {})
        if body:
            arguments = {"arguments": arguments, **body}
        result = self._rpc("tools/call", {"name": tool, "arguments": arguments}).json()["result"]
        return Reply(not result["isError"], result["structuredContent"], result["content"][0]["text"])

    def commit(self, tool: str, args: dict[str, Any], token: str, idem: str) -> Reply:
        return self.call(f"{tool}_commit", args, confirmation_token=token, idempotency_key=idem)


@dataclass
class Flow:
    """A gateway wired to the real API, and the stores to look at afterwards."""

    gw: Gateway
    world: Any

    def surface(self, kind: str, oid: str = USER_OID, conversation: str | None = None) -> Surface:
        if kind == "mcp":
            return McpSurface(self.gw, oid)
        return RestSurface(self.gw, oid, conversation or f"conv-{oid[:4]}")

    def events(self, oid: str = USER_OID):
        return sorted(self.world.audit.for_user(oid), key=lambda e: (e.occurred_at, e.event_seq))

    def history(self, client_id: int, program: str, year: int):
        return self.world.claims.history(client_id, program, year)


def seed_claims() -> None:
    """Computed claims for the book, recorded while the API is still open (no tokens yet)."""
    from fastapi.testclient import TestClient

    import main

    http = TestClient(main.app)
    for client_id, year, identified in SEEDS:
        response = http.post("/api/claims", json={
            "client_id": client_id, "program_code": "GA_JTC", "tax_year": year, "status": "assessed",
            "provenance": "computed", "decided_by": "analyst@example.com", "identified_usd": identified,
        })
        assert response.status_code == 201, response.text


def build_flow(tmp_path, world, transport: httpx.AsyncBaseTransport | None = None, **setting_overrides: Any) -> Flow:
    """The gateway around the real API app (or `transport`, to break the road to it), sharing the writer list and audit file with `world`."""
    import main

    gw = build_gateway(
        tmp_path, transport=transport or httpx.ASGITransport(app=main.app), token_provider=mint_app, writers={USER_OID}, **setting_overrides,
    )
    gw.services.pipeline._entitlement = world.writers
    gw.audit = world.audit
    return Flow(gw, world)


@pytest.fixture
def flow(request, tmp_path, monkeypatch, world, service, gold):  # noqa: F811
    """The real stack: the book and claims seeded, then Entra switched on, then the gateway around the real API."""
    monkeypatch.setattr(client_book, "clients", lambda: copy.deepcopy([*BOOK, PAYROLL_ROW, UNASSESSED_ROW]))
    seed_claims()
    request.getfixturevalue("entra")
    return build_flow(tmp_path, world)


@pytest.fixture(params=["rest", "mcp"])
def surface(request, flow) -> Surface:
    """The writer, reaching the gateway the orchestrator's way and then Cowork's."""
    return flow.surface(request.param)


def platform_text(reply: Reply) -> str:
    """The text a model is handed for a result, minus the frame: what the blocks render to."""
    return render_markdown(blocks_from(reply.body))


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _value(token: str) -> str:
    return token.replace(",", "")


def money_mutations(text: str) -> list[str]:
    """`text` with the last digit of each dollar figure changed in turn: one wrong figure per variant.

    A variant whose new figure equals ANOTHER number the text already holds is left out: the
    guard compares values, so "$0" changed to "$1" next to a real "1" is not a wrong figure it
    can see. That limit is real and is pinned on its own in `test_workflows_chaos`.
    """
    present = {_value(n) for n in NUMBER.findall(text)}
    variants = []
    for match in MONEY.finditer(text):
        end = match.end() - 1
        while not text[end].isdigit():
            end -= 1
        mutated = text[:end] + str((int(text[end]) + 1) % 10) + text[end + 1:]
        new_figure = _value(MONEY.search(mutated, match.start()).group()[1:])
        if new_figure not in present:
            variants.append(mutated)
    return variants

__all__ = ["OTHER_OID", "THIRD_OID", "USER_OID", "Reply", "flow", "surface", "world", "service", "gold", "entra"]


