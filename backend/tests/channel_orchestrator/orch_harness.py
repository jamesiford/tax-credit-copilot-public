"""A whole orchestrator around fakes: an ASGI gateway, a scripted model, a moving clock. [CH-08]

Nothing here is a network. The gateway is a FastAPI app the orchestrator's real `GatewayClient`
calls through `httpx.ASGITransport`; it answers `client_resolve` with the platform's own
deterministic resolver and every other tool with an envelope built through the platform's own
block helpers (so the blocks agree with the facts the way real ones do). The model is a script of
turns the real `ModelChain`, `PortChatClient` and MAF `Agent` consume, so the code under test is
the shipped code.
"""
from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator

from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.models import ModelChain, Provider
from app.core.planner import Planner
from app.core.settings import OrchestratorSettings, load_settings
from app.core.state import StateStore
from app.core.turn import TurnPipeline, TurnReply
from application import client_book
from application.capabilities import _support as s
from application.capabilities import catalog
from application.capabilities.client import client_resolve
from application.capabilities.envelope import Provenance
from domain.ai import ModelUnavailable, StreamEnd, TextDelta, ToolCall

TENANT = "00000000-0000-0000-0000-0000000000aa"
USER_OID = "bbbbbbbb-0000-4000-8000-000000000002"
OTHER_OID = "cccccccc-0000-4000-8000-000000000003"
BOOK = [
    {"account_id": 2001, "name": "Cascade Retail Partners", "industry": "Retail"},
    {"account_id": 2002, "name": "Northwind Care Systems", "industry": "Healthcare"},
    {"account_id": 2003, "name": "Ironbridge Logistics", "industry": "Logistics"},
]
ENV = {
    "CHANNEL_GATEWAY_URL": "https://gateway.example.test", "CHANNEL_GATEWAY_AUDIENCE": "api://gateway-test",
    "TENANT_ID": TENANT, "AI_PROVIDER_CHAIN": "gateway", "AI_GATEWAY_ENDPOINT": "https://models.example.test",
    "AI_GATEWAY_AUTH": "none", "FOUNDRY_AGENT_NAME": "tcc-channel-orchestrator", "FOUNDRY_AGENT_VERSION": "7",
}


def identity(oid: str = USER_OID, conversation: str = "conv-1", name: str = "Pat Writer") -> ActingIdentity:
    return ActingIdentity(oid, name, TENANT, "teams", conversation, "corr-1", "test")


class FakeClock:
    """A monotonic clock a test moves."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ------------------------------------------------------------------------ the model


class ScriptedChat:
    """A `ChatModel` that plays a script: each entry is one model turn (`tools`, `text`, or `error`)."""

    name = "gateway"

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script, self.seen = list(script), []

    def status(self):
        return None

    async def stream(self, messages, *, model, temperature=None, tools=()):
        self.seen.append({"messages": list(messages), "tools": [t.name for t in tools]})
        if not self.script:
            raise ModelUnavailable("script exhausted")
        step = self.script.pop(0)
        if step.get("delay"):
            await asyncio.sleep(step["delay"])
        if step.get("error"):
            raise ModelUnavailable(step["error"])
        for n, call in enumerate(step.get("tools", [])):
            yield ToolCall(f"call-{len(self.seen)}-{n}", call["tool"], json.dumps(call.get("args", {})))
        if step.get("text"):
            yield TextDelta(step["text"])
        yield StreamEnd(provider="gateway", model="test-model")


# ---------------------------------------------------------------------- the gateway


def _money(value: str) -> str:
    return s.cell(value, "money")


def _eligibility(args: dict[str, Any]) -> dict[str, Any]:
    pay = args.get("method") == "pay_period"
    credit = {"credit_name": "Georgia Jobs Tax Credit", "average_headcount": "494.25" if pay else "375.53",
              "prior_period_average_headcount": "310.50", "qualifying_jobs": "183.75" if pay else "65.03",
              "annual_credit_usd": "643125.00" if pay else "227605.00", "lifetime_credit_usd": "3215625.00" if pay else "1138025.00",
              "benefit_period_years": 5, "citation": "O.C.G.A. 48-7-40.1"}
    year = args["tax_year"]
    blocks = [s.heading(f"{credit['credit_name']} · TY{year}"), s.table(("Measure", "Value"), [
        ("Average headcount", s.cell(credit["average_headcount"], "headcount")),
        ("Qualifying jobs", s.cell(credit["qualifying_jobs"], "headcount")),
        ("Annual credit", _money(credit["annual_credit_usd"])),
        ("Lifetime credit", _money(credit["lifetime_credit_usd"])),
    ])]
    facts = {"snapshot": {"selected_client_id": args["client_id"], "selected_tax_year": year, "calculated": True}, "credit": credit}
    return s.result("client_eligibility", facts, blocks, provenance=Provenance(
        run_id="run-0001", rule_pack_version="rules/ga_jtc/2023.json", trail_sha256="ab" * 32, source="tcc_gold")).to_dict()


def _simple(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    facts = {"items": {"total": 3, "annual_value_usd": "31500.00"}, "tax_year": args.get("tax_year")}
    blocks = [s.heading(tool.replace("_", " ").title()), s.table(("Measure", "Value"), [
        ("Items", s.cell(3, "count")), ("Annual value", _money("31500.00"))])]
    return s.result(tool, facts, blocks, provenance=Provenance(source="recorded claims; no run")).to_dict()


def _book(args: dict[str, Any]) -> dict[str, Any]:
    rows = [{"name": c["name"], "band": "Identified", "identified_usd": v} for c, v in zip(BOOK, ("140000", "40495", "9900"))]
    blocks = [s.heading("Who to call"), s.table(("Client", "Band", "Identified"), [(r["name"], r["band"], _money(r["identified_usd"])) for r in rows])]
    return s.result("book_rank", {"rows": rows}, blocks, provenance=Provenance(source="recorded claims; no run")).to_dict()


def _trend(args: dict[str, Any]) -> dict[str, Any]:
    years = [{"tax_year": 2022, "annual_average": "410.13"}, {"tax_year": 2023, "annual_average": "494.25"}]
    blocks = [s.heading("Trend"), s.table(("Tax year", "Annual average"), [(s.cell(y["tax_year"], "year"), s.cell(y["annual_average"], "headcount")) for y in years])]
    return s.result("client_trend", {"years": years, "eligible_every_year_since_base": None}, blocks,
                    provenance=Provenance(run_id="run-0001", trail_sha256="cd" * 32)).to_dict()


def _prepare(tool: str, args: dict[str, Any], token: str) -> dict[str, Any]:
    base = tool.removesuffix("_prepare")
    preview = {"before": {"scope": "prospective"}, "after": {"scope": args.get("scope", "in_scope")}}
    facts = {"tool": base, "preview": preview, "confirmation": {"confirmation_id": f"c-{token}", "token": token, "expires_at": "later"}}
    blocks = [s.heading(f"Preview: {base.replace('_', ' ')}"), s.table(("Field", "Now", "After"), [("scope", "prospective", preview["after"]["scope"])]),
              s.callout("Nothing has changed yet. It is only written when you confirm.")]
    return s.result(tool, facts, blocks, provenance=Provenance(source="prepared change; nothing written"),
                    warnings=["Prepared only: no change is made until the confirmation is committed."]).to_dict()


@dataclass
class Call:
    tool: str
    args: dict[str, Any]
    body: dict[str, Any]
    headers: dict[str, str]


@dataclass
class FakeGateway:
    """The channel gateway, in process. Records every call; behaviour is overridable per tool."""

    writers: set[str] = field(default_factory=lambda: {USER_OID})
    overrides: dict[str, Callable[[dict[str, Any]], tuple[int, dict[str, Any]]]] = field(default_factory=dict)
    narration_status: int = 200
    delays: dict[str, float] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    narrations: list[dict[str, Any]] = field(default_factory=list)
    prepared: dict[str, dict[str, Any]] = field(default_factory=dict)
    committed: dict[str, dict[str, Any]] = field(default_factory=dict)

    def tools_called(self) -> list[str]:
        return [c.tool for c in self.calls]

    def app(self) -> FastAPI:
        api = FastAPI()

        @api.post("/channel/v1/tools/{tool}")
        async def run(tool: str, request: Request) -> JSONResponse:
            body = await request.json()
            self.calls.append(Call(tool, body.get("args", {}), body, {k.lower(): v for k, v in request.headers.items()}))
            await asyncio.sleep(self.delays.get(tool, 0))
            status, payload = self._answer(tool, body, request.headers.get("x-acting-user-oid", ""))
            return JSONResponse(status_code=status, content=payload)

        @api.post("/channel/v1/audit/narration")
        async def narration(request: Request) -> JSONResponse:
            self.narrations.append(await request.json())
            if self.narration_status != 200:
                return JSONResponse(status_code=self.narration_status, content={"error": {"code": "audit_unavailable", "message": "down"}})
            return JSONResponse(status_code=200, content={"audit_id": "a-1", "agent_action_recorded": True})

        return api

    def client(self) -> GatewayClient:
        return GatewayClient("http://gateway", lambda: "fake-token", transport=httpx.ASGITransport(app=self.app()))

    # ------------------------------------------------------------------ answers

    def _answer(self, tool: str, body: dict[str, Any], oid: str) -> tuple[int, dict[str, Any]]:
        args = body.get("args", {})
        if tool in self.overrides:
            return self.overrides[tool](args)
        spec = catalog.BY_NAME.get(tool)
        if spec is None:
            return 404, {"error": {"code": "unknown_tool", "message": f"no such tool: {tool}"}}
        errors = sorted(Draft202012Validator(spec.schema).iter_errors(args), key=lambda e: list(e.absolute_path))
        if errors and spec.kind != catalog.WRITE_COMMIT:
            return 422, {"error": {"code": "invalid_arguments", "message": errors[0].message, "retryable": False}}
        if spec.kind == catalog.WRITE_PREPARE:
            return self._prepare(tool, args, oid)
        if spec.kind == catalog.WRITE_COMMIT:
            return self._commit(tool, body, oid)
        return 200, self._read(tool, args)

    def _read(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool == "client_resolve":
            return client_resolve(args["name_or_text"], args.get("history", []), args.get("current_client_id")).to_dict()
        return {"client_eligibility": _eligibility, "book_rank": _book, "client_trend": _trend}.get(tool, lambda a: _simple(tool, a))(args)

    def _prepare(self, tool: str, args: dict[str, Any], oid: str) -> tuple[int, dict[str, Any]]:
        if oid not in self.writers:
            return 403, {"error": {"code": "not_authorized", "message": "this user is not entitled to make changes"}}
        token = f"tok-{len(self.prepared) + 1}"
        self.prepared[token] = {"oid": oid, "tool": tool.removesuffix("_prepare"), "args": copy.deepcopy(args), "used": False}
        return 200, _prepare(tool, args, token)

    def _commit(self, tool: str, body: dict[str, Any], oid: str) -> tuple[int, dict[str, Any]]:
        if oid not in self.writers:
            return 403, {"error": {"code": "not_authorized", "message": "this user is not entitled to make changes"}}
        held = self.prepared.get(body.get("confirmation_token") or "")
        sent = body.get("args") or {}
        if held is None:
            return self._refuse(404, "confirmation_unknown")
        if held["oid"] != oid:
            return self._refuse(403, "confirmation_wrong_user")
        if held["args"] != sent.get("arguments", sent):
            return self._refuse(422, "confirmation_wrong_args")
        if held["used"] and body.get("idempotency_key") not in self.committed:
            return self._refuse(409, "confirmation_replayed")
        replay = body["idempotency_key"] in self.committed
        held["used"] = True
        self.committed[body["idempotency_key"]] = held
        facts = {"tool": held["tool"], "replayed": replay, "result": {"status": "recorded"}}
        note = "Already done earlier; nothing was repeated." if replay else "Done. The change is recorded under your name."
        blocks = [s.heading(held["tool"].replace("_", " ")), s.paragraph(note)]
        return 200, s.result(tool, facts, blocks, provenance=Provenance(source="mediator command; audited")).to_dict()

    @staticmethod
    def _refuse(status: int, code: str) -> tuple[int, dict[str, Any]]:
        return status, {"error": {"code": code, "message": code.replace("_", " "), "retryable": False}}


# ------------------------------------------------------------------ the orchestrator


@dataclass
class Rig:
    """Everything a test drives: the pipeline, the fakes and the clock."""

    pipeline: TurnPipeline
    gateway: FakeGateway
    chat: ScriptedChat
    clock: FakeClock
    settings: OrchestratorSettings

    async def say(self, text: str, who: ActingIdentity | None | object = "default") -> TurnReply:
        """Say `text` as `who`: a person, the default test user, or `None` for nobody."""
        return await self.pipeline.handle(text, identity() if who == "default" else who)


def build_rig(
    script: list[dict[str, Any]] | None = None, *, supports_tools: bool = True, gateway: FakeGateway | None = None,
    env: dict[str, str] | None = None, configured: bool = True, client: GatewayClient | None = None,
) -> Rig:
    """A pipeline over a fake gateway (or a real one's `client`) and a scripted model. `configured=False` has no model."""
    from application.ai.safety.injection import PromptInjectionGuard

    settings = load_settings({**ENV, **(env or {})})
    gateway, clock, chat = gateway or FakeGateway(), FakeClock(), ScriptedChat(script or [])
    providers = [Provider("gateway", chat, "test-model", supports_tools)] if configured else []
    chain = ModelChain(providers, egress_policy=settings.ai.egress_policy, timeout_seconds=5.0,
                       injection=PromptInjectionGuard() if settings.ai.safety.injection_guard else None)
    pipeline = TurnPipeline(settings, client or gateway.client(), Planner(chain), StateStore(settings.state_ttl_seconds, clock), clock)
    return Rig(pipeline, gateway, chat, clock, settings)


def patch_book(monkeypatch) -> None:
    """The client book the platform's resolver reads."""
    monkeypatch.setattr(client_book, "clients_or_empty", lambda: copy.deepcopy(BOOK))
