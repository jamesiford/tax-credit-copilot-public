"""The run worker's entry points: the inline worker's on/off rule, the health endpoint, and `--once`.

Offline. It proves the entry point composes the real worker over the configured queue and that the platform's probe is
answered; it does not prove a deployed App Service starts it (see live-checks.md).
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

import pytest

from bootstrap import run_batch_wiring, run_worker
from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository


@pytest.fixture()
def repo():
    r = SqliteRunBatchRepository(":memory:")
    run_batch_wiring.set_run_batch_repository(r)
    yield r
    run_batch_wiring.set_run_batch_repository(None)
    r.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_inline_worker_follows_the_setting(monkeypatch, repo):
    monkeypatch.setenv("RUN_WORKER_INLINE", "false")
    assert run_worker.start_inline_worker() is None
    monkeypatch.setenv("RUN_WORKER_INLINE", "true")
    handle = run_worker.start_inline_worker()
    try:
        assert handle is not None and handle.done() is False
    finally:
        handle.cancel()


def test_an_inline_worker_in_a_deployed_process_warns(monkeypatch, repo, caplog):
    monkeypatch.setenv("ENVIRONMENT", "azure")
    monkeypatch.setenv("RUN_WORKER_INLINE", "true")
    with caplog.at_level("WARNING", logger="tcc.runs"):
        handle = run_worker.start_inline_worker()
    handle.cancel()
    assert any("single-instance trial" in r.message for r in caplog.records)


def test_the_health_endpoint_answers_200_and_404(repo):
    port = _free_port()
    server = run_worker.serve_health(port)
    try:
        body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5).read())
        assert body["status"] == "ok" and "counters" in body
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other", timeout=5)
        assert missing.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_once_drains_the_queue_and_exits_zero(repo, monkeypatch):
    assert run_worker.main(["--once"]) == 0
