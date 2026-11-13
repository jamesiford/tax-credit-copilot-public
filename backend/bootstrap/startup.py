"""Process start-up steps that need the composition root, kept out of `main.py` so the entrypoint stays readable."""
from __future__ import annotations

import logging


def start_ai(log: logging.Logger) -> None:
    """Validate model access now and warm publishing in the background.

    Settings are validated at start-up (a gateway with no auth scheme must stop startup, not the first question);
    publishing is warmed in the background so Foundry being slow or down never blocks the API. A provider that
    cannot warm leaves the scripted stream in place.
    """
    from bootstrap.wiring import get_agent_catalog, get_ai_settings, get_model_router

    settings = get_ai_settings()
    log.info("AI provider chain: %s", ", ".join(settings.provider_chain))
    get_model_router().statuses()
    get_agent_catalog().warm()
