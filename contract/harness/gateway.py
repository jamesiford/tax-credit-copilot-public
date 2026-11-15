"""Profile G1: the channel gateway in front of the in-process API, as the Teams / Copilot / Cowork channels reach it.

The API runs under Entra sign-in (`harness/auth.py`) and the gateway calls it through its `ApiClient` seam: the same class, with an
ASGI transport to the API app instead of the network, and a token provider that mints an app-only token (role `TCC.Agent`) with the
harness key. Callers authenticate to the gateway with tokens minted against the gateway audience.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from . import auth
from .world import World

GATEWAY_AUDIENCE = "api://contract-gateway"
GATEWAY_APP_ID = "00000000-0000-0000-0000-0000000000c1"
GATEWAY_ENV = {
    "TENANT_ID": auth.TENANT, "GATEWAY_AUDIENCE": GATEWAY_AUDIENCE, "API_BASE_URL": "http://api.contract.local", "API_AUDIENCE": auth.AUDIENCE,
    "ENVIRONMENT": "local", "CHANNEL_RATE_LIMIT_PER_MINUTE": "6", "CHANNEL_DEBUG_WHOAMI": "0",
}


def build(work: Path) -> World:
    import httpx

    from application import request_limits  # noqa: F401
    from bootstrap import channel_wiring
    from channel.api_client import ApiClient
    from channel.app import create_app
    from channel.config import load_settings
    from channel.ledger import FactLedger
    from channel.limiter import RateLimiter
    from domain.channel import WriterGrant
    from infrastructure.auth.entra import EntraTokenValidator

    from . import profiles
    from .control import ContractControl

    base = profiles.build("P1", work)
    auth.install(60)
    for name in ("CHANNEL_STORE",):
        pass
    settings = load_settings(dict(GATEWAY_ENV))
    api_control = ContractControl(base.app)
    transport = httpx.ASGITransport(app=api_control, raise_app_exceptions=False)
    api = ApiClient(settings, lambda: auth.mint({"kind": "agent", "roles": ["TCC.Agent"]}), transport=transport)
    validator = EntraTokenValidator(tenant_id=settings.tenant_id, api_audience=GATEWAY_AUDIENCE, jwks_client=auth.FakeJwks())
    app = create_app(settings, api=api, validator=validator, limiter=RateLimiter(settings.rate_limit_per_minute, clock=lambda: 0.0),
                     ledger=FactLedger(clock=lambda: 0.0))
    channel_wiring.get_writer_repository().grant(WriterGrant(user_oid=auth.OID_WRITER, added_by="contract", display_name="Writer"))
    original = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def both(gateway_app):
        """The gateway starts only after the API it calls has started and settled."""
        async with base.app.router.lifespan_context(base.app):
            await api_control.settle()
            async with original(gateway_app):
                yield

    app.router.lifespan_context = both
    return World("G1", work, base.warehouse, app, {"api": "P1"})
