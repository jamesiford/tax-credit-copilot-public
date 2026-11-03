"""The gateway's composition root. [CH-06]

Explicit, in one place, like `application/wiring.py` is for the API: what the gateway
is made of and where each piece comes from. It composes through
`application.channel_wiring` (audit trail, writer entitlement), which imports no
query, command or framework, so the gateway never loads the engine.

Every collaborator can be handed in, which is how the tests run the whole gateway
against a fake API and fake keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application import channel_wiring
from channel.api_client import ApiClient, managed_identity_token
from channel.auth import CallerAuthenticator
from channel.config import GatewaySettings
from channel.downloads import DownloadService
from channel.ledger import FactLedger
from channel.limiter import RateLimiter
from channel.mcp import McpServer
from channel.pipeline import ToolPipeline
from infrastructure.auth.entra import EntraTokenValidator

NAME = "tcc-channel-gateway"
VERSION = "0.1.0"


class _LazyEntitlement:
    """Resolves the writer entitlement on first use, so building the gateway touches no store."""

    def is_writer(self, user_oid: str) -> bool:
        return channel_wiring.get_writer_entitlement().is_writer(user_oid)


class _LazyAuditor:
    """The channel auditor, resolved per call so a swapped repository (a test's) takes effect."""

    def __getattr__(self, name: str) -> Any:
        return getattr(channel_wiring.get_channel_auditor(), name)


@dataclass
class Services:
    """Everything a route needs, composed."""

    settings: GatewaySettings
    authenticator: CallerAuthenticator
    pipeline: ToolPipeline
    downloads: DownloadService
    mcp: McpServer
    api: ApiClient


def build_services(
    settings: GatewaySettings, *, validator: EntraTokenValidator | None = None, api: ApiClient | None = None,
    auditor: Any = None, entitlement: Any = None, ledger: FactLedger | None = None, limiter: RateLimiter | None = None,
) -> Services:
    """Compose the gateway. Anything not handed in is built from `settings` and the environment."""
    validator = validator or EntraTokenValidator(tenant_id=settings.tenant_id, api_audience=settings.gateway_audience)
    api = api or ApiClient(settings, managed_identity_token(settings))
    auditor = auditor or _LazyAuditor()
    limiter = limiter or RateLimiter(settings.rate_limit_per_minute)
    authenticator = CallerAuthenticator(settings, validator)
    pipeline = ToolPipeline(
        settings=settings, auditor=auditor, entitlement=entitlement or _LazyEntitlement(), limiter=limiter,
        ledger=ledger or FactLedger(), api=api, version=VERSION,
    )
    downloads = DownloadService(settings=settings, auditor=auditor, api=api, limiter=limiter)
    mcp = McpServer(authenticator, pipeline, settings, NAME, VERSION)
    return Services(settings, authenticator, pipeline, downloads, mcp, api)
