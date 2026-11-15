"""Build the real app in process under a named profile. One factory, shared by the recorder, the checks and the real-server run.

Profiles
--------
P1 (fixture)    DATA_SOURCE=csv, the committed synthetic payroll, account 1001, SQLite operational stores in a temp directory,
                and the real `GoldWriter` / `GoldReader` on SQLite wired exactly as `backend/tests/data_engine_fixture.py` does.
P2 (lakehouse)  a local Delta lakehouse written with `tests/local_lakehouse.py` from `data.source.synth.SYNTHETIC_CLIENTS`, and a
                Gold store populated by running the engine for every synthetic client.

`World.open()` returns a live `httpx.AsyncClient` bound to the ASGI app (no sockets) with the app lifespan running, as uvicorn would.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from . import hermetic

PROFILES = ("P1", "P2", "G1", "G1L")


@dataclass
class World:
    profile: str
    work: Path
    warehouse: Any
    app: Any
    notes: dict[str, Any] = field(default_factory=dict)

    @contextlib.asynccontextmanager
    async def client(self, **kwargs: Any) -> AsyncIterator[Any]:
        import httpx

        from .control import ContractControl

        control = ContractControl(self.app)
        async with self.app.router.lifespan_context(self.app):
            await control.settle()
            transport = httpx.ASGITransport(app=control, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://contract.local", **kwargs) as http:
                yield http


def _wire_gold(warehouse: Any) -> None:
    from bootstrap import wiring
    from tests.data_engine_fixture import OfflineGoldWriter

    from .gold import ContractGoldReader

    wiring.set_gold_writer(OfflineGoldWriter(warehouse))
    wiring.set_gold_reader(ContractGoldReader(warehouse))
    # The governed data query (`data_catalog`, `data_query`, `data_distinct_values`) reads the same store through the SQLite adapter.
    from bootstrap import data_wiring
    from tests.data_engine_fixture import data_service

    data_wiring.set_data_query_service(data_service(warehouse))


def build(profile: str, workdir: Path | None = None) -> World:
    """Build the app for `profile` in a fresh directory. Stores, ids and the clock start from the same place every time."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; expected one of {PROFILES}")
    work = hermetic.apply(workdir or Path(tempfile.mkdtemp(prefix=f"tcc-contract-{profile.lower()}-")))
    from . import freeze

    freeze.reset_counters()
    from . import profiles

    return profiles.build(profile, work)
