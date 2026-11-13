"""The worker process may run as its own managed identity; by default it does not. [F07.3]"""
from __future__ import annotations

import os

from bootstrap import run_worker
from config import load_settings


def test_unset_leaves_the_identity_alone_and_set_selects_it_for_this_process(monkeypatch):
    monkeypatch.delenv("RUN_WORKER_IDENTITY_CLIENT_ID", raising=False)
    monkeypatch.setenv("AZURE_CLIENT_ID", "api-identity")
    assert run_worker.apply_worker_identity() is False and os.environ["AZURE_CLIENT_ID"] == "api-identity"
    monkeypatch.setenv("RUN_WORKER_IDENTITY_CLIENT_ID", "worker-identity-client-id-5555")
    assert run_worker.apply_worker_identity() is True
    assert os.environ["AZURE_CLIENT_ID"] == "worker-identity-client-id-5555"


def test_the_setting_defaults_to_empty_and_is_trimmed():
    assert load_settings({}).runs.worker_identity_client_id == ""
    assert load_settings({"RUN_WORKER_IDENTITY_CLIENT_ID": "  abc  "}).runs.worker_identity_client_id == "abc"


def test_the_log_never_carries_the_whole_client_id(monkeypatch, caplog):
    monkeypatch.setenv("RUN_WORKER_IDENTITY_CLIENT_ID", "worker-identity-client-id-5555")
    monkeypatch.setenv("AZURE_CLIENT_ID", "x")
    with caplog.at_level("INFO", logger="tcc.runs"):
        run_worker.apply_worker_identity()
    assert "5555" in caplog.text and "worker-identity" not in caplog.text


def test_the_inline_worker_does_not_change_the_apis_identity(monkeypatch):
    monkeypatch.setenv("RUN_WORKER_IDENTITY_CLIENT_ID", "should-not-apply")
    monkeypatch.setenv("AZURE_CLIENT_ID", "api-identity")
    monkeypatch.setenv("RUN_WORKER_INLINE", "false")
    assert run_worker.start_inline_worker() is None and os.environ["AZURE_CLIENT_ID"] == "api-identity"
