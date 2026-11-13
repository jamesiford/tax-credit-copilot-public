"""The live smoke script: guarded, GET-only, and truthful about every non-2xx. [F07.1]"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "live-smoke.py"


@pytest.fixture(scope="module")
def smoke():
    spec = importlib.util.spec_from_file_location("live_smoke", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["live_smoke"] = module
    spec.loader.exec_module(module)
    return module


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(handler))


def test_it_reads_every_global_endpoint_and_each_clients_reads_with_get_only(smoke):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/scope":
            return httpx.Response(200, json={"clients": [{"account_id": 7}]})
        if request.url.path == "/api/scope/client/7":
            return httpx.Response(200, json={"default_year": 2023, "states": ["GA"]})
        return httpx.Response(200, json={})

    report = smoke.run_smoke(_client(handler))
    assert not report.failures
    assert {m for m, _ in seen} == {"GET"}
    paths = {p for _, p in seen}
    assert set(smoke.GLOBAL_READS) <= paths
    assert {"/api/scope/client/7", "/api/eligibility/2023", "/api/v2/clients/7/units"} <= paths


def test_every_non_2xx_is_reported_with_the_error_code_not_the_body(smoke):
    def handler(request):
        if request.url.path == "/api/v2/portfolio":
            return httpx.Response(500, json={"detail": {"code": "footprint_guard", "secret": "do-not-echo"}})
        if request.url.path == "/api/rules":
            return httpx.Response(503, json={"detail": "source_lakehouse unavailable: not configured"})
        return httpx.Response(200, json={})

    report = smoke.run_smoke(_client(handler))
    failed = {c.path: (c.status, c.code) for c in report.failures}
    assert failed == {
        "/api/v2/portfolio": (500, "footprint_guard"),
        "/api/rules": (503, "source_lakehouse_unavailable_not_configured"),
    }
    assert "do-not-echo" not in smoke.render(report)


def test_the_client_refuses_anything_but_get(smoke):
    transport = smoke._ReadOnly(httpx.MockTransport(lambda r: httpx.Response(200)))
    with httpx.Client(base_url="http://x", transport=transport) as client:
        assert client.get("/a").status_code == 200
        with pytest.raises(smoke.TargetRefused):
            client.post("/a")
        with pytest.raises(smoke.TargetRefused):
            client.delete("/a")


def test_the_target_guard(smoke):
    env = {"SMOKE_TARGETS": "test=https://t.example,prod-eu=https://p.example,live=https://l.example", "SMOKE_PRODUCTION_TARGETS": "live"}
    assert smoke.resolve_target("local", {}) == "http://127.0.0.1:8000"
    assert smoke.resolve_target("test", env) == "https://t.example"
    for name in ("prod-eu", "live"):
        with pytest.raises(smoke.TargetRefused, match="production"):
            smoke.resolve_target(name, env)
        assert smoke.resolve_target(name, env, allow_production=True)
    with pytest.raises(smoke.TargetRefused, match="unknown target"):
        smoke.resolve_target("https://anywhere.example", env)
    with pytest.raises(smoke.TargetRefused, match="loopback"):
        smoke.resolve_target("local", {"SMOKE_LOCAL_URL": "https://not-local.example"})


def test_main_exit_codes(smoke, monkeypatch, capsys):
    assert smoke.main(["--target", "nowhere"]) == smoke.EXIT_GUARD
    assert "GUARD REFUSED" in capsys.readouterr().err


def test_against_the_in_process_app_every_read_answers_or_names_its_cause(smoke):
    from fastapi.testclient import TestClient

    from main import app

    report = smoke.run_smoke(TestClient(app, raise_server_exceptions=False))
    assert {"/api/ready", "/api/v2/programs", "/api/rules", "/api/v2/run-batches"} <= {c.path for c in report.checks if c.ok}
    assert all(c.code for c in report.failures), "a failure without a code cannot be acted on"
