"""The gateway app factory. [CH-06]

`create_app()` reads the environment, refuses to build under a bad configuration and
returns the FastAPI app. It is a factory so the tests can build a gateway around fakes
and so importing this module never needs the environment; `channel.main` is the one
module that calls it at import, because gunicorn wants a module-level `app`.

No docs, schema or other framework routes are served: the public surface is the list
in `channel.routes` and nothing else.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from channel.config import GatewaySettings, load_settings
from channel.routes import build_router
from channel.wiring import NAME, VERSION, Services, build_services

log = logging.getLogger("tcc.channel")


def create_app(settings: GatewaySettings | None = None, **overrides: Any) -> FastAPI:
    """Build the gateway. `overrides` are `build_services` collaborators (the fakes of a test)."""
    settings = settings or load_settings()
    services: Services = build_services(settings, **overrides)
    if not settings.caller_channels:
        log.warning(
            "CHANNEL_CALLER_CHANNELS is not set: any registered caller may assert Teams or Copilot Chat. "
            "Bind each caller to the channels it serves (docs/m365-channel/DATA-ACCESS.md, RM-02).",
        )
    if settings.debug_whoami:
        log.warning(
            "CHANNEL_DEBUG_WHOAMI is ON: the channel_ping diagnostic is offered and echoes the acting-user headers as received. "
            "Demo and identity spikes only; switch it off afterwards (docs/m365-channel/DEMO-CLEANUP.md).",
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("%s %s starting (deployed=%s, store=%s)", NAME, VERSION, settings.deployed, settings.channel_store)
        yield
        await services.api.close()

    app = FastAPI(title="Tax Credit Copilot channel gateway", version=VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.services = services

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled gateway error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": {
            "code": "internal_error", "message": "the gateway failed unexpectedly", "retryable": True}})

    app.include_router(build_router(services))
    return app
