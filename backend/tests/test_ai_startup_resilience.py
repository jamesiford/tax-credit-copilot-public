"""A model being unreachable never stops the app starting or the engine answering. [AI-04]

Readiness is about whether this process can serve the engine's figures. Foundry or a
gateway being down is reported by `/api/health` as degraded; it is not a reason for
the platform to take the instance out of rotation, because the engine needs no model.
"""
from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.chat as chat
from api.chat.degraded import UNAVAILABLE_SENTENCE

BRIEF = "Brief.\n\nJSON:\n" + json.dumps({"identified_usd": "31000.00"})


def _offline(monkeypatch, **env):
    for name in ("FOUNDRY_PROJECT_ENDPOINT", "APPLICATIONINSIGHTS_CONNECTION_STRING"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("TCC_WARM_ON_START", "0")
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def test_startup_and_readiness_survive_an_unreachable_gateway(monkeypatch):
    import main
    from bootstrap import wiring

    _offline(monkeypatch, AI_PROVIDER_CHAIN="gateway", AI_GATEWAY_ENDPOINT="https://127.0.0.1:9",
             AI_GATEWAY_AUTH="none", AI_MODEL_NARRATOR__GATEWAY="m", AI_MODEL_ROUTER__GATEWAY="m",
             AI_MODEL_ANALYSIS__GATEWAY="m")
    wiring.reset_ai()
    with TestClient(main.app) as client:
        ready = client.get("/api/ready").json()
        assert ready["ready"] is True and ready["warm"]["status"] == "skipped"
        assert client.get("/api/health").status_code == 200


def test_startup_and_readiness_survive_foundry_failing_to_publish(monkeypatch):
    import main
    from bootstrap import wiring
    from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog

    def failing_warm(self):
        self._state, self._detail = "unavailable", "ConnectError"

    monkeypatch.setattr(FoundryAgentCatalog, "warm", failing_warm)
    _offline(monkeypatch, FOUNDRY_PROJECT_ENDPOINT="https://unreachable.invalid", AI_PROVIDER_CHAIN="foundry")
    wiring.reset_ai()
    with TestClient(main.app) as client:
        assert client.get("/api/ready").json()["ready"] is True
        health = client.get("/api/health").json()
        assert health["ai"]["state"] in {"degraded", "disabled"} and "unavailable" in json.dumps(health["ai"])


def test_an_unreachable_gateway_still_gets_the_reader_the_engines_figures(monkeypatch):
    from bootstrap import wiring

    for name, value in {"AI_PROVIDER_CHAIN": "gateway", "AI_GATEWAY_ENDPOINT": "https://127.0.0.1:9",
                        "AI_GATEWAY_AUTH": "none", "AI_MODEL_NARRATOR__GATEWAY": "m",
                        "AI_MODEL_ROUTER__GATEWAY": "m", "AI_MODEL_ANALYSIS__GATEWAY": "m"}.items():
        monkeypatch.setenv(name, value)
    wiring.reset_ai()

    async def go():
        token = chat._TELEMETRY_CONTEXT.set({"app": SimpleNamespace(state=SimpleNamespace()), "request_id": "r", "intent": "book"})
        try:
            return [f async for f in chat._stream_agent("ReportingAgent", BRIEF)]
        finally:
            chat._TELEMETRY_CONTEXT.reset(token)

    shown = "".join(json.loads(m)["content"] for m in re.findall(r"event: token\ndata: (.*)\n", "".join(asyncio.run(go()))))
    assert shown.startswith(UNAVAILABLE_SENTENCE) and "- identified_usd: 31000.00" in shown
