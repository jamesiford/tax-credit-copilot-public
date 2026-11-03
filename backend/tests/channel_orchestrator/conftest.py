"""Fixtures for the orchestrator tests. [CH-08]

The orchestrator is a separate deployable, so its tests put `channel_orchestrator/` on the path and
build its vendored copy of the platform's shared modules before anything imports it. In this run the
backend's own packages of the same names win (`app/__init__.py` appends the vendored path), and
`test_orch_vendor.py` proves the vendored copy imports on its own.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = ROOT / "channel_orchestrator"

subprocess.run([sys.executable, str(ROOT / "scripts" / "vendor-orchestrator.py")], check=True, capture_output=True)
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))

from orch_harness import patch_book  # noqa: E402


@pytest.fixture(autouse=True)
def book(monkeypatch):
    patch_book(monkeypatch)
