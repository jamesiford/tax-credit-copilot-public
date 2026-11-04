"""One world, five doors: the same capability reached by REST, the gateway, MCP, the MAF tools and the portal chat. [RM-13]

The parity test is only worth anything if the doors share nothing but the platform: so this builds the
real stack once and drives it the way each client does.

    rest-api      `POST /api/capabilities/{tool}` with a signed-in person's token (the portal's REST)
    rest-gateway  `POST /channel/v1/tools/{tool}` as the orchestrator does (an app token, the acting person in headers)
    mcp           `POST /mcp` `tools/call` with a Cowork person's delegated token, inside an initialised session
    maf           the generated MAF `FunctionTool`, invoked with a real `ToolRunner` over the real gateway client
    portal        `POST /api/chat`, the real pipelines, a fixed fake narrator that remembers every brief it was handed

Everything behind them is real: the gateway app, the API app (`main.app`, entra on), the capabilities and the engine,
which replayed the synthetic payroll into a SQLite Gold store (`tests/data_engine_fixture.py`). No model takes part;
the narrator is a stub that writes one token. Nothing here computes, rounds or reformats a figure.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "channel"))

from app.core.gateway_client import GatewayClient  # noqa: E402
from app.core.maf_catalog_tools import TURN, catalog_tool  # noqa: E402
from app.core.state import ConversationState  # noqa: E402
from app.core.tools import ToolRunner  # noqa: E402
from application import client_book, wiring  # noqa: E402
from application.capabilities import catalog  # noqa: E402
from application.data_wiring import set_data_query_service  # noqa: E402
from domain.channel import WriterGrant  # noqa: E402
from gateway_harness import USER_OID, agent_headers, agent_token, build_gateway, user_headers, user_token  # noqa: E402
from infrastructure.persistence.sqlite_claims import SqliteClaimRepository  # noqa: E402
from orch_harness import BOOK, identity  # noqa: E402
from tests.data_engine_fixture import CLIENT, YEAR, SqliteGoldReader, SqliteWarehouse, data_service, run_engine  # noqa: E402
from tests.test_agent_principal import entra, mint_app  # noqa: E402,F401 - fixtures
from tests.test_auth import OID as PORTAL_OID  # noqa: E402
from tests.test_auth import mint  # noqa: E402
from tests.test_channel_writes import world  # noqa: E402,F401 - fixture

#: The synthetic client the engine run holds, named for the book.
BOOK_WITH_RUN = [{"account_id": CLIENT, "name": "Synthetic Client One", "industry": "Restaurants"}, *BOOK]
SURFACES = ("rest-api", "rest-gateway", "mcp", "maf", "portal")


@dataclass(frozen=True)
class Seen:
    """What one door returned: the status, the envelope (or error body) and whatever else only that door adds."""

    surface: str
    status: int
    body: dict[str, Any]
    extra: dict[str, Any]


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """The synthetic payroll through the real engine into a SQLite Gold store, with the claim the run recorded."""
    directory = tmp_path_factory.mktemp("parity")
    warehouse, claims = SqliteWarehouse(), SqliteClaimRepository(directory / "claims.db")
    run_engine(warehouse, directory, claims)
    yield warehouse, claims
    claims.close()


class Rig:
    """The five doors over one world."""

    def __init__(self, gateway: Any, api: TestClient, monkeypatch: pytest.MonkeyPatch, world: Any) -> None:
        self.gw, self.api, self.monkeypatch, self.world = gateway, api, monkeypatch, world
        self.orchestrator = GatewayClient("http://gateway", agent_token, transport=httpx.ASGITransport(app=gateway.client.app))
        self.briefs: list[tuple[str, str]] = []

    # --------------------------------------------------------------------------------- REST

    def rest_api(self, tool: str, args: dict[str, Any], **body: Any) -> Seen:
        """The portal's REST door: a signed-in person straight to the API."""
        response = self.api.post(
            f"/api/capabilities/{tool}", json={"args": args, **body}, headers={"Authorization": f"Bearer {mint()}"},
        )
        return Seen("rest-api", response.status_code, response.json(), {})

    def rest_gateway(self, tool: str, args: dict[str, Any], channel: str = "teams", **body: Any) -> Seen:
        """The gateway's REST door, as the orchestrator calls it."""
        response = self.gw.client.post(
            f"/channel/v1/tools/{tool}", json={"args": args, **body}, headers=agent_headers(channel=channel),
        )
        return Seen("rest-gateway", response.status_code, response.json(), {})

    # ---------------------------------------------------------------------------------- MCP

    def mcp(self, tool: str, args: dict[str, Any]) -> Seen:
        """MCP `tools/call` inside a session a Cowork person opened."""
        headers = user_headers(user_token())
        opened = self.gw.client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, headers=headers,
        )
        session = opened.headers["mcp-session-id"]
        response = self.gw.client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}},
            headers={**headers, "Mcp-Session-Id": session},
        )
        result = response.json()["result"]
        status = 200 if not result["isError"] else self._error_status(result["structuredContent"])
        return Seen("mcp", status, result["structuredContent"], {"text": result["content"][0]["text"], "is_error": result["isError"]})

    @staticmethod
    def _error_status(body: dict[str, Any]) -> int:
        return 0 if "error" not in body else 422

    # ---------------------------------------------------------------------------------- MAF

    def runner(self, who: Any = None, question: str = "") -> ToolRunner:
        """A real turn's tool state over the real gateway client."""
        return ToolRunner(self.orchestrator, who or identity(), ConversationState(), question, 8, 300)

    def maf(self, tool: str, args: dict[str, Any], who: Any = None) -> Seen:
        """The generated `FunctionTool`, invoked the way the agent loop invokes it, over the real gateway."""
        from agent_framework import FunctionInvocationContext

        spec, turn = catalog.BY_NAME[tool], self.runner(who)
        function = catalog_tool(spec)
        context = FunctionInvocationContext(function=function, arguments=args, kwargs={TURN: turn})
        reply = asyncio.run(function.invoke(arguments=args, context=context))
        return Seen("maf", reply.status, reply.body, {"turn": turn})

    # --------------------------------------------------------------------------- a whole turn

    def teams(self, question: str, tool: str, proposed: dict[str, Any]) -> Seen:
        """A real orchestrator turn: the reader's words, a scripted model that names `tool`, the composer, the real gateway.

        The model's sentence is fixed: it is made of the placeholders the tool's own brief offered, so what the
        reader sees is the composer's substitution of the engine's figures and nothing a model wrote.
        """
        from orch_harness import build_rig

        turn = build_rig([{"tools": [{"tool": tool, "args": proposed}]}], client=self.orchestrator)
        narrator = FixedNarrator(turn.chat.stream)
        turn.chat.stream = narrator.stream
        reply = asyncio.run(turn.say(question, identity(USER_OID)))
        return Seen("maf-turn", 200 if reply.kind == "answer" else 0, {}, {"reply": reply, "narration": narrator.said, "narrator": narrator})

    # -------------------------------------------------------------------------------- portal

    def portal(self, intent: str, message: str, scope: dict[str, Any]) -> Seen:
        """The portal's chat over the real pipelines, with a narrator that writes one token and keeps its briefs."""
        import api.chat.dispatch as dispatch
        import api.chat.pipelines_briefs as briefs
        import api.chat.pipelines_core as core
        import api.chat.pipelines_whatif as whatif
        from api.chat.sse import _sse

        taken: list[tuple[str, str]] = []

        async def narrate(agent_name, prompt, **_):
            taken.append((agent_name, prompt))
            yield _sse("agent_start", {"agent": agent_name})
            yield _sse("token", {"agent": agent_name, "content": "Narration."})
            yield _sse("agent_end", {"agent": agent_name})

        async def plan(*_args, **_kwargs):
            return [intent]

        for module in (briefs, core, whatif):
            self.monkeypatch.setattr(module, "_stream_agent", narrate)
        self.monkeypatch.setattr(dispatch, "_plan", plan)
        self.monkeypatch.setattr(wiring, "get_narration_service", lambda: SimpleNamespace(available=lambda _agents: True))
        response = self.api.post(
            "/api/chat", json={"message": message, "client_confirmed": True, **scope},
            headers={"Authorization": f"Bearer {mint()}"},
        )
        events = _events(response.text)
        self.briefs += taken
        return Seen("portal", response.status_code, {}, {"events": events, "briefs": taken})


class FixedNarrator:
    """The model after its tool call: one sentence of placeholders, each copied from the brief it was handed.

    It picks the first figure path the brief offered (a money, headcount, count or number) and the last, so a
    narration is made of exactly what the composer will substitute. A brief that offers no figure gets a
    sentence with none. Deterministic, so the same facts always give the same narration.
    """

    FIGURE_FORMATS = ("money", "headcount", "count", "number")

    def __init__(self, first: Any) -> None:
        self._first, self.said, self.handed = first, "", ""

    async def stream(self, messages, *, model, temperature=None, tools=()):
        from domain.ai import StreamEnd, TextDelta

        tool_reply = [m for m in messages if m.role == "tool"]
        if not tool_reply:
            async for event in self._first(messages, model=model, temperature=temperature, tools=tools):
                yield event
            return
        self.handed = json.dumps([str(m) for m in messages])
        paths = [p for p in json.loads(tool_reply[-1].content).get("fact_paths", []) if p.get("format") in self.FIGURE_FORMATS]
        chosen = [paths[0]["placeholder"], paths[-1]["placeholder"]] if paths else []
        self.said = ("The figures are " + " and ".join(chosen) + ".") if chosen else "Here is the answer."
        yield TextDelta(self.said)
        yield StreamEnd(provider="gateway", model="test-model")


def _events(stream: str) -> list[tuple[str, dict[str, Any]]]:
    """The SSE frames of one answer, in order."""
    out, name = [], ""
    for line in stream.splitlines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            out.append((name, json.loads(line[6:])))
    return out


@pytest.fixture
def rig(engine, entra, world, tmp_path, monkeypatch):  # noqa: F811
    """The real gateway in front of the real API, over the engine's Gold store, with the book and the writers set."""
    import main

    warehouse, claims = engine
    wiring.set_gold_reader(SqliteGoldReader(warehouse))
    set_data_query_service(data_service(warehouse))
    wiring.set_claim_repository(claims)
    monkeypatch.setattr(client_book, "clients_or_empty", lambda: list(BOOK_WITH_RUN))
    monkeypatch.setattr(client_book, "clients", lambda: list(BOOK_WITH_RUN))
    world.writers.grant(WriterGrant(user_oid=PORTAL_OID, added_by="test"))
    gateway = build_gateway(tmp_path, transport=httpx.ASGITransport(app=main.app), token_provider=mint_app, writers={USER_OID})
    gateway.services.pipeline._entitlement = world.writers
    gateway.audit = world.audit
    try:
        yield Rig(gateway, TestClient(main.app), monkeypatch, world)
    finally:
        wiring.set_gold_reader(None)
        set_data_query_service(None)
