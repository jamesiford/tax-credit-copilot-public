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

from config import get_settings

_log = logging.getLogger(__name__)
_initialized = False


#: Words that mean the exporter is being refused or cannot authenticate, as opposed to a transient blip.
_AUTH_FAILURE_MARKERS = ("403", "forbidden", "clientauthenticationerror", "authorization", "credentialunavailable", "unauthorized")


class _ExporterAuthFilter(logging.Filter):
    """Say ONCE why the exporter is refused, then keep the repeats out of the log.

    The Azure Monitor exporter retries a refused export on every batch and logs each one, which buries
    the log under one cause. Everything that is not an authorisation failure passes through untouched.
    """

    def __init__(self) -> None:
        super().__init__()
        self._said = False

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage().lower()
        if not any(marker in text for marker in _AUTH_FAILURE_MARKERS):
            return True
        if not self._said:
            self._said = True
            _log.warning(
                "Application Insights refused the telemetry export (authorisation). Likely causes: Entra "
                "authentication is not enabled on the Application Insights resource, this identity lacks the "
                "'Monitoring Metrics Publisher' role on it, or the wrong identity is in use (check AZURE_CLIENT_ID "
                "and `az login`). The app continues without telemetry; set TELEMETRY_ENABLED=false to stop trying."
            )
        return False


def _where(name: str) -> str:
    """Where a setting's value came from. An OS variable overrides `.env`, which is the usual surprise."""
    try:
        from dotenv import dotenv_values, find_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a backend dependency
        return "the environment"
    path = find_dotenv(usecwd=True)
    from_file = dotenv_values(path) if path else {}
    current = get_settings().environ.get(name)
    if name not in from_file:
        return "the OS environment" if current is not None else "nowhere (unset)"
    if (from_file.get(name) or "") == (current or ""):
        return f"{path} (or an identical OS variable)"
    return "the OS environment, which overrides the value in .env"


def telemetry_enabled() -> bool:
    """On when `TELEMETRY_ENABLED` says so; otherwise on only if a connection string is set."""
    observability = get_settings().observability
    has_string = bool(observability.appinsights_connection_string)
    if observability.telemetry_enabled is None:
        return has_string
    return observability.telemetry_enabled and has_string


def configure_telemetry(service_name: str = "tax-credit-copilot-api") -> None:
    """Idempotent. Enables OpenTelemetry -> Application Insights when configured."""
    global _initialized
    if _initialized:
        return
    observability = get_settings().observability
    conn = observability.appinsights_connection_string
    source = _where("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if observability.telemetry_enabled is False:
        _log.info("Telemetry disabled: TELEMETRY_ENABLED=false (set in %s).", _where("TELEMETRY_ENABLED"))
        _initialized = True
        return
    if not conn:
        _log.info("Telemetry disabled: APPLICATIONINSIGHTS_CONNECTION_STRING is empty or unset (from %s).", source)
        _initialized = True
        return
    _log.info("Telemetry enabled: APPLICATIONINSIGHTS_CONNECTION_STRING is set (from %s).", source)
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        from infrastructure.azure_credential import shared_credential

        # The shared DefaultAzureCredential resolves the container's user-assigned managed
        # identity in Azure and a developer's `az login` locally, so this is one
        # code path rather than a branch on environment.
        credential = shared_credential()

        logging.getLogger("azure.monitor.opentelemetry.exporter").addFilter(_ExporterAuthFilter())
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
    if not telemetry_enabled():
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        return True
    except Exception:  # noqa: BLE001 — telemetry must never take the app down
        _log.exception("Failed to instrument FastAPI; continuing without request telemetry.")
        return False
