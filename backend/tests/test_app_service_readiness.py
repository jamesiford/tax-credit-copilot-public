"""The API is ready for App Service: gunicorn startup and a readiness probe. [HOST-1]"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent


def _offline(monkeypatch):
    """Start the app without reaching Foundry or App Insights from a local .env."""
    for name in ("FOUNDRY_PROJECT_ENDPOINT", "APPLICATIONINSIGHTS_CONNECTION_STRING"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("TCC_WARM_ON_START", "0")


def test_ready_is_false_before_startup_and_true_after(monkeypatch):
    import main

    _offline(monkeypatch)
    client = TestClient(main.app)
    assert client.get("/api/ready").json()["ready"] is False, "no lifespan has run yet"
    with TestClient(main.app) as started:
        body = started.get("/api/ready").json()
        assert body["ready"] is True and body["warm"]["status"] == "skipped"


def test_ready_waits_for_a_running_warm_up(monkeypatch):
    import main

    _offline(monkeypatch)
    with TestClient(main.app) as client:
        main.app.state.warm = {"status": "running"}
        assert client.get("/api/ready").json()["ready"] is False
        main.app.state.warm = {"status": "failed", "detail": "x"}
        assert client.get("/api/ready").json()["ready"] is True, "a failed warm-up is degraded, not down"


def test_startup_runs_gunicorn_with_uvicorn_workers_on_the_platform_port():
    script = (BACKEND / "startup.sh").read_bytes()
    assert b"\r" not in script, "a CRLF in a shell script breaks it on Linux"
    text = script.decode("utf-8")
    assert text.startswith("#!/bin/sh")
    assert "gunicorn -k uvicorn.workers.UvicornWorker" in text
    assert "${WEB_CONCURRENCY:-2}" in text and "0.0.0.0:${PORT:-8000}" in text
    assert "--timeout 600" in text and "main:app" in text


def test_gunicorn_is_a_declared_dependency():
    assert "gunicorn==" in (BACKEND / "requirements.txt").read_text(encoding="utf-8")
