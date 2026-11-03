"""A gateway under test: fake keys, a fake or real API, an in-memory audit trail. [CH-06]

Everything the gateway depends on is handed in, so a test drives the real app,
pipeline, authenticator and MCP server through `httpx.ASGITransport` with nothing
external: tokens are minted with a throwaway RSA key and verified against a fake JWKS
(`tests.test_auth`), the API is an in-process ASGI app (`FakeApi`, or the real one in
the integration tests) and the audit trail is SQLite in memory.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient

from application.acting_user import HEADER as ACTING_HEADER
from application.acting_user import parse_acting_user
from application.capabilities.envelope import Block, ToolResult
from application.channel_audit import ChannelAuditor
from channel.api_client import ApiClient
from channel.app import create_app
from channel.config import GatewaySettings
from channel.limiter import RateLimiter
from infrastructure.auth.entra import EntraTokenValidator, issuer_for
from infrastructure.persistence.sqlite_channel import SqliteChannelAuditRepository
from tests.test_auth import _KEY, FakeJwks

TENANT = "00000000-0000-0000-0000-0000000000aa"
OTHER_TENANT = "00000000-0000-0000-0000-0000000000bb"
GATEWAY_CLIENT_ID = "22222222-3333-4444-5555-666666666666"
GATEWAY_AUDIENCE = f"api://{GATEWAY_CLIENT_ID}"
API_AUDIENCE = "api://11111111-2222-3333-4444-555555555555"
ORCHESTRATOR_OID = "aaaaaaaa-0000-4000-8000-000000000001"
ORCHESTRATOR_APP = "99999999-8888-4777-8666-555555555555"
USER_OID = "bbbbbbbb-0000-4000-8000-000000000002"
OTHER_OID = "cccccccc-0000-4000-8000-000000000003"


def settings(**overrides: Any) -> GatewaySettings:
    base = dict(tenant_id=TENANT, gateway_audience=GATEWAY_AUDIENCE, api_base_url="http://api",
                api_audience=API_AUDIENCE, request_timeout_seconds=5.0, rate_limit_per_minute=600)
    return GatewaySettings(**{**base, **overrides})


def _mint(claims: dict[str, Any]) -> str:
    now = int(time.time())
    full = {"aud": GATEWAY_CLIENT_ID, "iss": issuer_for(TENANT), "iat": now, "nbf": now, "exp": now + 3600,
            "tid": TENANT, **claims}
    return jwt.encode({k: v for k, v in full.items() if v is not None}, _KEY, algorithm="RS256", headers={"kid": "test-key"})


def agent_token(*, roles: tuple[str, ...] | None = ("Channel.Invoke",), app_id: str | None = ORCHESTRATOR_APP, **extra: Any) -> str:
    """An app-only token for the orchestrator: no `scp`, no user name, `sub` equal to `oid`."""
    return _mint({"oid": ORCHESTRATOR_OID, "sub": ORCHESTRATOR_OID, "idtyp": "app", "azp": app_id,
                  "roles": list(roles) if roles is not None else None, **extra})


def user_token(*, scp: str | None = "Channel.Access", oid: str = USER_OID, **extra: Any) -> str:
    """A Cowork user's delegated token."""
    return _mint({"oid": oid, "sub": "subject-of-" + oid, "preferred_username": "pat@example.com", "name": "Pat Writer",
                  "scp": scp, **extra})


def agent_headers(token: str | None = None, **overrides: str | None) -> dict[str, str]:
    """The headers an orchestrator sends. Pass `name=None` to drop a header."""
    headers: dict[str, str | None] = {
        "Authorization": f"Bearer {token or agent_token()}", "X-Acting-User-Oid": USER_OID,
        "X-Acting-User-Name": "Pat Writer", "X-Acting-Tenant": TENANT, "X-Channel": "teams",
        "X-Conversation-Id": "conv-1", "X-Correlation-Id": "corr-1",
    }
    names = {"oid": "X-Acting-User-Oid", "name": "X-Acting-User-Name", "tenant": "X-Acting-Tenant",
             "channel": "X-Channel", "conversation": "X-Conversation-Id", "correlation": "X-Correlation-Id"}
    for key, value in overrides.items():
        headers[names.get(key, key)] = value
    return {k: v for k, v in headers.items() if v is not None}


def user_headers(token: str | None = None, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or user_token()}", **extra}


def envelope(tool: str, facts: dict[str, Any] | None = None, *, run_id: str | None = "run-1") -> dict[str, Any]:
    """A canned tool result, as the API would return it."""
    from application.capabilities.envelope import Provenance

    result = ToolResult(
        tool=tool, facts=facts if facts is not None else {"credit": {"annual_credit_usd": "31500.00"}, "tax_year": 2023},
        blocks=(Block("heading", text="Result"), Block("paragraph", text="The credit is $31,500.00.")),
        provenance=Provenance(run_id=run_id, trail_sha256="ab" * 32 if run_id else None),
    )
    return result.to_dict()


@dataclass
class FakeApi:
    """An in-process stand-in for `POST /api/capabilities/{tool}`; records what it was asked."""

    replies: dict[str, Any] = field(default_factory=dict)
    delay: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    artifact: bytes = b"PK\x03\x04 workbook"

    def app(self) -> FastAPI:
        api = FastAPI()

        @api.post("/api/capabilities/{tool}")
        async def capability(tool: str, request: Request) -> Response:
            return await self._answer(tool, request)

        @api.get("/api/health")
        def health(request: Request) -> dict[str, str]:
            self.paths.append(request.url.path)
            return {"status": "ok"}

        @api.get("/api/clients/{client_id}/artifacts/{artifact_id}")
        def artifact(client_id: int, artifact_id: str, request: Request) -> Response:
            self.paths.append(request.url.path)
            self.calls.append({"tool": "artifact", "acting": self._acting(request)})
            return Response(self.artifact, media_type="application/octet-stream", headers={"X-Content-SHA256": "f" * 64})

        return api

    def _acting(self, request: Request):
        return parse_acting_user(request.headers.get(ACTING_HEADER), TENANT)

    async def _answer(self, tool: str, request: Request) -> Response:
        import asyncio

        self.paths.append(request.url.path)
        body = await request.json()
        self.calls.append({
            "tool": tool, "body": body, "acting": self._acting(request),
            "correlation": request.headers.get("x-correlation-id"), "authorization": request.headers.get("authorization"),
        })
        if self.delay:
            await asyncio.sleep(self.delay)
        reply = self.replies.get(tool, (200, envelope(tool)))
        status, payload = reply(body) if callable(reply) else reply
        return JSONResponse(status_code=status, content=payload)

    def transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.app())


@dataclass
class Gateway:
    """A built gateway and everything a test wants to look at."""

    client: TestClient
    audit: SqliteChannelAuditRepository
    api: FakeApi | None
    ledger: Any
    clock: "Clock"
    writers: set[str]
    services: Any
    actions: Any = None

    def events(self, oid: str = USER_OID):
        return sorted(self.audit.for_user(oid), key=lambda e: (e.occurred_at, e.event_seq))


class Clock:
    """A clock a test moves."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Writers:
    """A `WriterEntitlement` over a mutable set."""

    def __init__(self, oids: set[str]) -> None:
        self.oids = oids

    def is_writer(self, oid: str) -> bool:
        return oid in self.oids


def build_gateway(
    tmp_path: Any, *, api: FakeApi | None = None, transport: httpx.AsyncBaseTransport | None = None,
    token_provider: Callable[[], str] = lambda: "api-token", writers: set[str] | None = None, **setting_overrides: Any,
) -> Gateway:
    """The real gateway app around fakes. Give `api` (a `FakeApi`) or a ready `transport`.

    The audit trail is a SQLite FILE, not `:memory:`: the adapter keeps one connection
    per thread, and the app runs on a different thread from the test.
    """
    from application.agent_audit import AgentActionRecorder
    from channel.ledger import FactLedger
    from channel.narration import NarrationAudit
    from infrastructure.persistence.sqlite_channel import SqliteAgentActionAuditRepository

    gw_settings = settings(**setting_overrides)
    audit = SqliteChannelAuditRepository(tmp_path / "audit.db")
    actions = SqliteAgentActionAuditRepository(tmp_path / "actions.db")
    clock, ledger = Clock(), FactLedger()
    writer_set = {USER_OID} if writers is None else writers
    fake = api or (FakeApi() if transport is None else None)
    api_client = ApiClient(gw_settings, token_provider, transport=transport or fake.transport())
    app = create_app(
        gw_settings, validator=EntraTokenValidator(tenant_id=TENANT, api_audience=GATEWAY_AUDIENCE, jwks_client=FakeJwks()),
        api=api_client, auditor=ChannelAuditor(audit), entitlement=Writers(writer_set), ledger=ledger,
        limiter=RateLimiter(gw_settings.rate_limit_per_minute, clock=clock),
    )
    app.state.services.narration = NarrationAudit(ChannelAuditor(audit), AgentActionRecorder(actions))
    return Gateway(TestClient(app), audit, fake, ledger, clock, writer_set, app.state.services, actions)


def correlation() -> str:
    return uuid.uuid4().hex
