"""Entry point: `gunicorn ... channel.main:app` (see `startup-channel.sh`). [CH-06]

The only module that builds the app at import. A misconfiguration raises here, so a
gateway that must not serve never binds a port.
"""
from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()  # local development; deployed settings come from the host.

from telemetry import configure_telemetry, instrument_fastapi  # noqa: E402
from channel.app import create_app  # noqa: E402
from config import get_settings  # noqa: E402

logging.basicConfig(level=get_settings().runtime.log_level)
configure_telemetry("tax-credit-copilot-channel")
app = create_app()
instrument_fastapi(app)
