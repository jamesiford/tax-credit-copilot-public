"""OAuth 2.0 client-credentials authentication, with a token cache. [AI-03]

The token is fetched once and reused until shortly before it expires; concurrent
callers wait on one refresh rather than each hitting the token endpoint (a lock,
not a stampede). `invalidate()` drops the cached token so a 401 from the gateway
leads to a fresh one on the next attempt.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping

import httpx

from application.ai.gateway_settings import GatewaySettings
from domain.ai import ModelAuth, ModelUnavailable

#: Refresh this long before the stated expiry, so a token never dies in flight.
SKEW_SECONDS = 60.0


class OAuthClientCredentials:
    """OAuth2 client-credentials: fetches a token, caches it until shortly before expiry, one fetch at a time."""

    def __init__(
        self, settings: GatewaySettings, *, client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings, self._clock = settings, clock
        self._client = client
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()
        self.fetches = 0

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            s = self._settings
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(s.timeout_s, connect=s.connect_timeout_s), verify=s.tls_verify,
            )
        return self._client

    async def headers(self) -> Mapping[str, str]:
        if self._token is None or self._clock() >= self._expires_at:
            async with self._lock:
                if self._token is None or self._clock() >= self._expires_at:
                    await self._refresh()
        return {"Authorization": f"Bearer {self._token}"}

    def invalidate(self) -> None:
        self._token, self._expires_at = None, 0.0

    async def _refresh(self) -> None:
        s = self._settings
        data = {"grant_type": "client_credentials", "client_id": s.oauth_client_id,
                "client_secret": s.oauth_client_secret}
        if s.oauth_scope:
            data["scope"] = s.oauth_scope
        try:
            response = await self._http().post(s.oauth_token_url, data=data)
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"the gateway token endpoint is unreachable ({type(exc).__name__})") from exc
        if response.status_code in (400, 401, 403):
            raise ModelAuth(f"the gateway token endpoint refused our client credentials ({response.status_code})")
        if response.status_code >= 400:
            raise ModelUnavailable(f"the gateway token endpoint answered {response.status_code}")
        body = response.json()
        token = body.get("access_token")
        if not token:
            raise ModelAuth("the gateway token endpoint returned no access_token")
        self.fetches += 1
        self._token = token
        self._expires_at = self._clock() + max(float(body.get("expires_in", 300)) - SKEW_SECONDS, 0.0)

    def __repr__(self) -> str:
        return "OAuthClientCredentials(secret=<redacted>)"
