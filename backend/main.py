"""FastAPI entrypoint. Phase 2: agents registered in Foundry on startup."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()  # local dev — production env vars come from the host.

from telemetry import configure_telemetry, instrument_fastapi  # noqa: E402
from api.artifacts import router as artifacts_router  # noqa: E402
from api.auth import request_guard, router as auth_router  # noqa: E402
from api.chat import router as chat_router  # noqa: E402
from api.claims import router as claims_router, v2_router as claims_v2_router  # noqa: E402
from api.eligibility import router as eligibility_router  # noqa: E402
from api.rules import router as rules_router  # noqa: E402
from api.forecast import router as forecast_router  # noqa: E402
from api.onezero import router as onezero_router  # noqa: E402
from api.retroactive import router as retroactive_router  # noqa: E402
from api.rules_ingestion import router as rules_ingestion_router  # noqa: E402
from api.simulate import router as simulate_router  # noqa: E402
from api.summary import router as summary_router  # noqa: E402
from api.ingestion import router as ingestion_router  # noqa: E402
from api.findings import router as findings_router  # noqa: E402
from api.proximity import router as proximity_router  # noqa: E402
from api.scope import router as scope_router  # noqa: E402
from api.trend import router as trend_router  # noqa: E402
from api.workspace import router as workspace_router  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("tax-credit-copilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Before anything else: a deployed process with a non-durable store or no
    # stated data classification must not serve a single request. [DATA-5, D26]
    from application.deployment import check_deployment_configuration

    app.state.deployment = check_deployment_configuration()
    log.info("deployment configuration: %s", app.state.deployment)

    configure_telemetry("tax-credit-copilot-api")
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL", "gpt-5.4-mini")

    app.state.registry = None
    app.state.agent_metrics = {}
    app.state.agent_spans = []
    app.state.audit_events = []
    if not endpoint:
        log.warning(
            "FOUNDRY_PROJECT_ENDPOINT is not set; agents will NOT be registered. "
            "/api/chat will fall back to the Phase 1 scripted stream."
        )
    else:
        log.info("Registering agents in Foundry (endpoint=%s, model=%s) ...", endpoint, model)
        try:
            from agents import build_all
            registry = build_all()
            app.state.registry = registry
            log.info("=" * 72)
            log.info("Foundry agent registry ready. Open in the portal:")
            for r in registry:
                log.info("  %-22s v%-3s id=%s", r.name, r.version, r.agent_id)
                log.info("    %s", r.portal_url)
            log.info("=" * 72)
        except Exception:
            log.exception("Failed to register Foundry agents; /api/chat will use the Phase 1 stub.")
            app.state.registry = None

    # Pay the cold-lakehouse cost off the request path. Never blocks startup, and
    # a lakehouse that is unreachable degrades to a slow first request.
    from application.warmup import should_warm, warm_read_paths

    app.state.warm = {"status": "skipped"}
    warm_task = None
    if should_warm():
        from api.workspace import _service as workspace_service

        async def _warm() -> None:
            app.state.warm = {"status": "running"}
            try:
                report = await asyncio.to_thread(
                    warm_read_paths,
                    warm_workspace=lambda: workspace_service().summary(),
                )
                app.state.warm = {"status": "ready", **report}
            except Exception as exc:
                log.warning("warm-up abandoned: %s", type(exc).__name__)
                app.state.warm = {"status": "failed", "detail": type(exc).__name__}

        warm_task = asyncio.create_task(_warm())

    # The pool goes cold on its own. `prewarm` fills it once; without something
    # holding the links open they hit the ODBC pool's 60s idle timeout and the
    # next request pays a full handshake — 3.2s against 120ms.
    keepalive_task = None
    if should_warm():
        from application.warmup import keepalive_interval_s, touch_warehouse

        async def _keepalive() -> None:
            interval = keepalive_interval_s()
            while True:
                await asyncio.sleep(interval)
                try:
                    await asyncio.to_thread(touch_warehouse)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - never reaches a request
                    log.debug("keepalive skipped: %s", type(exc).__name__)

        keepalive_task = asyncio.create_task(_keepalive())

    app.state.started = True
    yield
    app.state.started = False
    for task in (warm_task, keepalive_task):
        if task is not None and not task.done():
            task.cancel()
    log.info("API shutting down.")


# Every route authenticates the caller and authorizes each client it names,
# except the platform's health and readiness probes. [AUTH-3, D24]
app = FastAPI(
    title="Tax Credit Copilot API",
    version="0.3.0",
    lifespan=lifespan,
    dependencies=[Depends(request_guard)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)

# Must run here, before the app serves: middleware cannot be added once the
# stack is built, and the lifespan runs inside the first call that builds it.
instrument_fastapi(app)


@app.get("/api/ready")
def ready() -> dict:
    """True once startup has finished and the read paths are warm. [HOST-1]

    `/api/health` answers as soon as the process serves; this answers whether
    the first real page will be fast. A warm-up that failed still counts as
    ready: the warm-up is an optimisation, and the request path retries on its
    own.
    """
    warm = getattr(app.state, "warm", {"status": "unknown"})
    started = bool(getattr(app.state, "started", False))
    return {"ready": started and warm.get("status") != "running", "warm": warm}


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "phase": 2,
        "foundry_configured": bool(os.getenv("FOUNDRY_PROJECT_ENDPOINT")),
        "agents_registered": bool(getattr(app.state, "registry", None)),
        "telemetry_configured": bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")),
        "warm": getattr(app.state, "warm", {"status": "unknown"}),
    }


app.include_router(auth_router)
app.include_router(artifacts_router)
app.include_router(chat_router)
app.include_router(claims_router)
app.include_router(claims_v2_router)
app.include_router(eligibility_router)
app.include_router(rules_router)
app.include_router(forecast_router)
app.include_router(onezero_router)
app.include_router(retroactive_router)
app.include_router(rules_ingestion_router)
app.include_router(simulate_router)
app.include_router(summary_router)
app.include_router(ingestion_router)
app.include_router(findings_router)
app.include_router(proximity_router)
app.include_router(scope_router)
app.include_router(trend_router)
app.include_router(workspace_router)
