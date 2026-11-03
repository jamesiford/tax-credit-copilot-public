"""The mock gateway, importable for tests. [AI-03]

`scripts/mock-ai-gateway.py` has a hyphen, so it is loaded by path. `gateway()`
returns the app, an `httpx.AsyncClient` talking to it in-process, and a record of
which responses were closed — the observable for "abandoning a stream stops the
upstream call".
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import httpx

from application.ai.gateway_settings import GatewaySettings

_PATH = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "mock-ai-gateway.py"


def load_mock_module():
    if "mock_ai_gateway" in sys.modules:
        return sys.modules["mock_ai_gateway"]
    spec = importlib.util.spec_from_file_location("mock_ai_gateway", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mock_ai_gateway"] = module
    spec.loader.exec_module(module)
    return module


class _TrackedStream(httpx.AsyncByteStream):
    def __init__(self, inner, closed: list):
        self._inner, self._closed = inner, closed

    async def __aiter__(self):
        async for chunk in self._inner:
            yield chunk

    async def aclose(self):
        self._closed.append(True)
        await self._inner.aclose()


class _TrackingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner, closed: list):
        self._inner, self._closed = inner, closed

    async def handle_async_request(self, request):
        response = await self._inner.handle_async_request(request)
        response.stream = _TrackedStream(response.stream, self._closed)
        return response


def gateway(closed: list | None = None, **config):
    """`(mock_state, client, closed)` for a mock gateway with `config`.

    Pass a list as `closed` to observe when the adapter closes a response.
    """
    module = load_mock_module()
    app = module.create_app(module.MockConfig(**config))
    closed = [] if closed is None else closed
    transport = _TrackingTransport(httpx.ASGITransport(app=app, raise_app_exceptions=False), closed)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.invalid")
    return app.state.mock, client, closed


def settings(**overrides) -> GatewaySettings:
    base = dict(endpoint="https://mock.invalid", auth="none")
    base.update(overrides)
    return GatewaySettings(**base)
