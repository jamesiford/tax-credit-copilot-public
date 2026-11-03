"""Entra token authentication: the managed identity, no secret. [AI-03]

The preferred scheme when the gateway can validate Entra tokens or accept
federation. `DefaultAzureCredential` is `az login` locally and the managed
identity deployed; azure-identity caches and refreshes the token itself, so this
only asks for one per request. The blocking call runs in a thread so a slow
metadata endpoint cannot stall the event loop that is streaming other answers.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from domain.ai import ModelAuth


class EntraTokenAuth:
    def __init__(self, audience: str, *, credential: Any = None) -> None:
        if not audience:
            raise ValueError("entra_token auth needs AI_GATEWAY_ENTRA_AUDIENCE")
        self._scope = audience.rstrip("/") + "/.default" if not audience.endswith("/.default") else audience
        self._credential = credential

    def _cred(self) -> Any:
        if self._credential is None:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
        return self._credential

    async def headers(self) -> Mapping[str, str]:
        try:
            token = await asyncio.to_thread(self._cred().get_token, self._scope)
        except Exception as exc:  # noqa: BLE001 - any credential failure is an auth failure
            raise ModelAuth(f"could not obtain an Entra token for the gateway ({type(exc).__name__})") from exc
        return {"Authorization": f"Bearer {token.token}"}

    def invalidate(self) -> None:
        return None
