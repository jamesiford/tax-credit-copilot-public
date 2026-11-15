"""Hermetic process configuration, applied from `contract/` at run time. No product file is edited.

`apply()` must run before `main` (or any product module that calls `load_dotenv`) is imported. It:

* puts `backend/` and `backend/tests/` on `sys.path` (the test helpers are imported read-only);
* turns `load_dotenv` into a no-op, as `backend/tests/conftest.py` does, so a developer's `.env` is never read;
* sets the same pinned environment the suite uses and points every SQLite store at a temp directory;
* installs a socket guard that raises on any outbound connection;
* freezes the clock and every id source (see `freeze.py`).
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
TESTS = BACKEND / "tests"

#: Every variable the harness pins. Anything else a developer has set is removed by `_scrub`.
PINNED = {
    "DATA_SOURCE": "csv",
    "FIXTURE_ACCOUNT_ID": "1001",
    "REFERENCE_ACCOUNT_ID": "1001",
    "DATA_CLASSIFICATION": "synthetic",
    "ENVIRONMENT": "local",
    "AUTH_MODE": "none",
    "TCC_WARM_ON_START": "0",
    "PYTHONUTF8": "1",
}

#: Prefixes of live-service configuration that must never reach a hermetic run.
_LIVE_PREFIXES = (
    "FABRIC_", "WAREHOUSE_", "FOUNDRY_", "AZURE_", "APPLICATIONINSIGHTS_", "APPINSIGHTS_",
    "OPENAI_", "ANTHROPIC_", "MODEL_", "AI_", "CHANNEL_", "ORCHESTRATOR_", "ENTRA_", "AUTH_",
)

_installed = False


def assert_checkout() -> None:
    """Halt (hard stop 2) if the product code imported is not this worktree's."""
    import domain

    where = Path(domain.__file__).resolve()
    if ROOT not in where.parents:
        raise SystemExit(f"HALT: imported {where}, which is outside the contract worktree {ROOT}")

class NetworkBlocked(RuntimeError):
    """Raised by the socket guard: a hermetic run attempted an outbound connection."""


def _guard_sockets() -> None:
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _allowed(address) -> bool:
        # asyncio's self-pipe and the in-process ASGI transport use socketpair (AF_UNIX / loopback pair);
        # the real-server run of stage C6 is the only thing that binds loopback, and it does so in another process.
        return isinstance(address, tuple) and address and address[0] in ("127.0.0.1", "::1", "localhost") and os.environ.get("CONTRACT_ALLOW_LOOPBACK") == "1"

    def connect(self, address):
        if _allowed(address):
            return real_connect(self, address)
        raise NetworkBlocked(f"outbound connection blocked by the contract harness: {address!r}")

    def connect_ex(self, address):
        if _allowed(address):
            return real_connect_ex(self, address)
        raise NetworkBlocked(f"outbound connection blocked by the contract harness: {address!r}")

    def getaddrinfo(host, *args, **kwargs):
        if host in ("localhost", "127.0.0.1", "::1", None, ""):
            return _real_getaddrinfo(host, *args, **kwargs)
        raise NetworkBlocked(f"name resolution blocked by the contract harness: {host!r}")

    _real_getaddrinfo = socket.getaddrinfo
    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def _scrub() -> None:
    for name in list(os.environ):
        if name.startswith(_LIVE_PREFIXES) and name not in PINNED:
            del os.environ[name]


def apply(workdir: Path | None = None) -> Path:
    """Configure the process once. Returns the temp directory the stores live in."""
    global _installed
    for path in (str(BACKEND), str(TESTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    assert_checkout()
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False  # type: ignore[assignment]
    _scrub()
    os.environ.update(PINNED)
    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="tcc-contract-"))
    work.mkdir(parents=True, exist_ok=True)
    os.environ["OPERATIONAL_DB"] = str(work / "operational.db")
    if not _installed:
        _guard_sockets()
        from . import freeze

        freeze.install()
        _installed = True
    return work
