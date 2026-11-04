"""API-key authentication: one header, one secret. [AI-03]"""
from __future__ import annotations

from collections.abc import Mapping


class ApiKeyAuth:
    """`<header>: <prefix><key>`. The prefix is configurable because gateways differ
    (`Authorization: Bearer …`, `x-api-key: …`, `api-key: …`)."""

    def __init__(self, header: str, prefix: str, key: str) -> None:
        if not header or not key:
            raise ValueError("api_key auth needs a header name and a key")
        self._header, self._value = header, f"{prefix}{key}"

    async def headers(self) -> Mapping[str, str]:
        return {self._header: self._value}

    def invalidate(self) -> None:
        return None

    def __repr__(self) -> str:
        return f"ApiKeyAuth(header={self._header!r}, key=<redacted>)"
