"""`RunManifestRepository` in process memory. CI and local development only.

**This is not a warehouse and must never be mistaken for one.** It exists so the
test suite and a fresh clone run with no ODBC driver, no Azure credential and no
Fabric capacity — the same reason `sqlite_claims.py` exists beside
`warehouse_claims.py`.

What it does NOT give you, and what shipping it by accident would cost:

  - nothing survives a process restart
  - nothing is shared between replicas, so two containers disagree about
    whether a client has been assessed
  - nothing is queryable by Power BI, which is half the point of Gold

A deployed environment must set `RUN_MANIFEST_STORE=fabric`. This adapter
records that it is a stand-in on the instance itself, so a caller that wants to
assert it is talking to the real store can, and a diagnostic endpoint has
something honest to report.
"""
from __future__ import annotations

from domain.warehouse import RunManifest


class InMemoryRunManifestRepository:
    """`RunManifestRepository` over a dict. Durable for exactly one process."""

    #: Read by callers that need to prove they are not talking to a stand-in.
    is_durable = False

    def __init__(self) -> None:
        self._runs: dict[str, RunManifest] = {}

    def record(self, manifest: RunManifest) -> RunManifest:
        if manifest.run_id in self._runs:
            raise ValueError(
                f"run_id={manifest.run_id!r} is already recorded. Matching the "
                f"warehouse adapter, which has to guard this itself because "
                f"Fabric does not enforce the primary key."
            )
        self._runs[manifest.run_id] = manifest
        return manifest

    def get(self, run_id: str) -> RunManifest | None:
        return self._runs.get(run_id)

    def latest(self, client_id: int, *, program_code: str | None = None) -> RunManifest | None:
        live = [
            run for run in self._runs.values()
            if run.client_id == client_id
            and run.run_status == "success"
            and run.superseded_by_run_id is None
            and (program_code is None or run.program_code == program_code)
        ]
        return max(live, key=lambda run: run.run_started_at) if live else None

    def count(self) -> int:
        return len(self._runs)
