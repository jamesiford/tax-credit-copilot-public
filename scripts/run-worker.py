"""Start the run worker from the repository root: `python scripts/run-worker.py [--once]`. [ADR-012]

A thin launcher for `python -m bootstrap.run_worker` that puts `backend/` on the path and loads `backend/.env`, so it
works from the repo root the way the other operator scripts do. It changes nothing by itself: it leases queued items
and runs them through the existing run and assess commands, so what it does is what a batch asked for.

    python scripts/run-worker.py            # work until stopped
    python scripts/run-worker.py --once     # work until the queue is empty, then exit

Locally use `RUN_MANIFEST_STORE=sqlite` so this process and the API share one queue file.
"""
from __future__ import annotations

import sys

import sql_common as common


def main() -> int:
    common.load_env()
    from bootstrap.run_worker import main as run

    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
