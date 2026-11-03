"""Request authentication for the model gateway. [AI-03]

Three schemes behind one tiny interface, because the customer's gateway scheme is
unknown and must be a configuration choice, not a code change. In order of
preference: an Entra token for the app's managed identity (no secret anywhere),
OAuth client credentials (a secret, held as a Key Vault reference), an API key
(the same). `none` exists for the mock gateway and local development only.

An authenticator returns the headers for ONE request and may be asked to forget
what it holds (`invalidate`) when the gateway answers 401, so a rotated or
expired credential is picked up on the next attempt instead of failing until a
restart. Nothing here logs a header or a secret.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from application.ai.gateway_settings import GatewaySettings


class RequestAuthenticator(Protocol):
    """Supplies auth headers for one request."""

    async def headers(self) -> Mapping[str, str]: ...

    def invalidate(self) -> None: ...


class NoAuth:
    """No credentials. Never valid for a real gateway; settings refuse it deployed."""

    async def headers(self) -> Mapping[str, str]:
        return {}

    def invalidate(self) -> None:
        return None


def build_authenticator(settings: GatewaySettings, *, client: httpx.AsyncClient | None = None,
                        credential: Any = None) -> RequestAuthenticator:
    """The authenticator `settings.auth` names. `client` and `credential` are test seams."""
    from infrastructure.ai.auth.api_key import ApiKeyAuth
    from infrastructure.ai.auth.entra_token import EntraTokenAuth
    from infrastructure.ai.auth.oauth_client_credentials import OAuthClientCredentials

    if settings.auth == "api_key":
        return ApiKeyAuth(settings.api_key_header, settings.api_key_prefix, settings.api_key)
    if settings.auth == "oauth_client_credentials":
        return OAuthClientCredentials(settings, client=client)
    if settings.auth == "entra_token":
        return EntraTokenAuth(settings.entra_audience, credential=credential)
    return NoAuth()
