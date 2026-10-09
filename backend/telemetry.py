"""Application Insights wiring. Safe to call from anywhere; no-op when unset.

**Entra-authenticated, not key-authenticated.** The connection string carries an
InstrumentationKey, and on its own that key is a bearer credential: anyone
holding it can write telemetry into our workspace. Passing a `credential`
switches ingestion to Entra, so the managed identity is what authorises the
write and the key alone is not enough.

That leaves the deployed container with **no secret in its environment at all**.
Every other dependency was already keyless — Foundry has
`disableLocalAuth: true`, ACR has `adminUserEnabled: false`, and Storage and
OneLake authenticate the same identity — so this was the last one, and closing
it is why the stack needs no Key Vault.
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)
_initialized = False


def configure_telemetry(service_name: str = "tax-credit-copilot-api") -> None:
    """Idempotent. Enables OpenTelemetry → Application Insights when configured."""
    global _initialized
    if _initialized:
        return
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        _log.info("APPLICATIONINSIGHTS_CONNECTION_STRING not set; telemetry disabled.")
        _initialized = True
        return
    try:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.opentelemetry import configure_azure_monitor

        # DefaultAzureCredential resolves the container's user-assigned managed
        # identity in Azure and a developer's `az login` locally, so this is one
        # code path rather than a branch on environment.
        credential = DefaultAzureCredential(
            managed_identity_client_id=os.getenv("AZURE_CLIENT_ID") or None
        )

        configure_azure_monitor(
            connection_string=conn,
            credential=credential,
            resource_attributes={"service.name": service_name},
        )
        _log.info("Application Insights enabled via Entra (service=%s).", service_name)
    except Exception:  # noqa: BLE001 — telemetry must never take the app down
        # Deliberately broad and deliberately non-fatal. An identity that cannot
        # reach Azure Monitor is a monitoring problem; refusing to start would
        # turn it into an outage.
        _log.exception("Failed to initialize Azure Monitor; continuing without telemetry.")
    _initialized = True


def instrument_fastapi(app) -> bool:
    """Emit a request span per call to `app`. No-op unless App Insights is set.

    `configure_azure_monitor` instruments FastAPI by patching the CLASS, which
    only reaches apps constructed after it runs. Ours is constructed at import
    and configured in the lifespan, so without this the API sent traces and
    dependencies but not one request — and `requests` is what the runbook reads.
    The tracer resolves through the global provider, so configuring later works.
    """
    if not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        return True
    except Exception:  # noqa: BLE001 — telemetry must never take the app down
        _log.exception("Failed to instrument FastAPI; continuing without request telemetry.")
        return False
