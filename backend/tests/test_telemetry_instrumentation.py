"""Request telemetry reaches the app instance, not just the FastAPI class.

A13 smoke found App Insights holding traces and dependencies from the API but
no requests: the distro patches `fastapi.FastAPI`, and ours is constructed
before the lifespan configures it.
"""
from __future__ import annotations

from fastapi import FastAPI

import telemetry


def test_no_connection_string_means_no_instrumentation(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    app = FastAPI()

    assert telemetry.instrument_fastapi(app) is False
    assert not getattr(app, "_is_instrumented_by_opentelemetry", False)


def test_a_configured_app_instance_is_instrumented(monkeypatch):
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=00000000-0000-0000-0000-000000000000",
    )
    app = FastAPI()

    assert telemetry.instrument_fastapi(app) is True
    assert app._is_instrumented_by_opentelemetry is True


def test_the_api_instruments_its_own_instance_at_import():
    source = (telemetry.__file__.replace("telemetry.py", "main.py"))
    with open(source, encoding="utf-8") as handle:
        text = handle.read()

    assert "instrument_fastapi(app)" in text
    assert text.index("instrument_fastapi(app)") < text.index("@app.get(\"/api/ready\")")
