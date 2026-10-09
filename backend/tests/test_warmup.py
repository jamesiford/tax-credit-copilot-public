"""Warm-up must never be the reason the API is down.

It exists to move a cold-lakehouse cost off the request path — `/api/scope`
alone has been measured at 58 seconds and then a connect timeout. That makes it
a convenience, so every failure mode has to degrade to "the first request is
slow" rather than to a broken app.
"""
from __future__ import annotations

import pytest

from application.warmup import should_warm, warm_read_paths


def test_warming_is_skipped_when_the_cost_is_a_local_file(monkeypatch):
    """`conftest` pins DATA_SOURCE=csv, so the suite must never pay for this."""
    monkeypatch.setenv("DATA_SOURCE", "csv")
    assert should_warm() is False


def test_warming_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    for value in ("0", "false", "no"):
        monkeypatch.setenv("TCC_WARM_ON_START", value)
        assert should_warm() is False


def test_warming_is_on_by_default_against_the_lakehouse(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    monkeypatch.delenv("TCC_WARM_ON_START", raising=False)
    assert should_warm() is True


def test_a_step_that_fails_is_reported_not_raised():
    def boom():
        raise TimeoutError("cold delta log")

    report = warm_read_paths(warm_workspace=boom)

    workspace = next(s for s in report["steps"] if s["step"] == "sealed_workspace")
    assert workspace["ok"] is False
    assert "TimeoutError" in workspace["detail"]
    # The steps after it still ran.
    assert any(s["step"] == "trend" for s in report["steps"])


def test_every_step_is_timed_so_a_slow_one_can_be_named():
    report = warm_read_paths(warm_workspace=lambda: None)

    assert report["total_seconds"] >= 0
    for step in report["steps"]:
        assert step["seconds"] >= 0
        assert step["step"]
