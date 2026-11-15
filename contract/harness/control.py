"""Harness-only control surface, wrapped around the app as ASGI middleware so the product's routes and guards are untouched.

An implementation under test (the .NET host) must offer the same three hooks under `/__contract__/` for `replay.py` to drive it:

    POST /__contract__/drain   run every queued run-batch item to completion, synchronously; 200 {"drained": <n>}
    POST /__contract__/env     body {"set": {NAME: value}, "unset": [NAME]}: change process configuration for the steps that follow
    POST /__contract__/reset   (optional) restore the seed state; otherwise the replay tool starts a fresh server per scenario

None of these exist in the product: a request for them against the unwrapped app is a 404.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

PREFIX = "/__contract__/"


class ContractControl:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def settle(self, timeout: float = 120.0) -> None:
        """Wait for the start-up work the app runs in the background (store check, source-schema check).

        `/api/ready` reports both while they run, so a recording taken early would capture a race. The recorder starts only
        once they have finished; an implementation under test should do the same before it accepts the replay.
        """
        state = self.app.state
        waited = 0.0
        while waited < timeout:
            stores = getattr(state, "stores", {"status": "running"}).get("status")
            schema = getattr(state, "source_schema", {"status": "running"}).get("status")
            if stores != "running" and schema != "running":
                return
            await asyncio.sleep(0.05)
            waited += 0.05

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            async def gated(message: dict) -> None:
                if message["type"] == "lifespan.startup.complete":
                    await self.settle()
                await send(message)

            await self.app(scope, receive, gated)
            return
        if scope["type"] != "http" or not scope["path"].startswith(PREFIX):
            await self.app(scope, receive, send)
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        status, payload = await self._handle(scope["path"][len(PREFIX):], scope["method"], body)
        data = json.dumps(payload).encode()
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
        await send({"type": "http.response.body", "body": data})

    async def _handle(self, name: str, method: str, body: bytes) -> tuple[int, dict]:
        if method != "POST":
            return 405, {"detail": "POST only"}
        if name == "drain":
            from bootstrap.run_worker import build_worker

            drained = await asyncio.to_thread(build_worker().drain)
            return 200, {"drained": drained}
        if name == "env":
            spec = json.loads(body or b"{}")
            for key, value in (spec.get("set") or {}).items():
                os.environ[key] = str(value)
            for key in spec.get("unset") or []:
                os.environ.pop(key, None)
            _after_env_change()
            return 200, {"set": sorted(spec.get("set") or {}), "unset": sorted(spec.get("unset") or [])}
        return 404, {"detail": "unknown control"}


def _after_env_change() -> None:
    """Drop the singletons that cache configuration the way the product's own tests do when they change it."""
    try:
        from api import workspace
        from tools.reference_workspace import ReferenceWorkspaceService

        workspace._SERVICE = ReferenceWorkspaceService(source_kind=os.environ.get("DATA_SOURCE", "csv"))
    except Exception:  # noqa: BLE001 - control surface, best effort
        pass
