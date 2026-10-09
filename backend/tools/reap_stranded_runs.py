"""Close out runs that died with their process. Safe to re-run.

Marks `running` manifests older than the threshold as `failed`, leaving
`run_completed_at` NULL because the run never completed. Never deletes.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from infrastructure.persistence.fabric_warehouse import (  # noqa: E402
    OPS_SCHEMA,
    STRANDED_RUN_MINUTES,
    FabricWarehouseConnection,
)
from infrastructure.persistence.warehouse_gold import GoldWriter  # noqa: E402


def _show(title: str) -> None:
    with FabricWarehouseConnection().scope() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT client_id, run_id, tax_year, run_status, run_started_at, run_completed_at "
            f"FROM {OPS_SCHEMA}.run_manifest WHERE run_status IN ('running', 'failed') "
            f"ORDER BY run_started_at"
        )
        print(f"\n-- {title}")
        for row in cur.fetchall():
            print("   ", " | ".join("" if v is None else str(v) for v in row))


if __name__ == "__main__":
    print(f"threshold: {STRANDED_RUN_MINUTES} minutes")
    _show("running / failed BEFORE")
    reaped = GoldWriter().reap_stranded_runs()
    print(f"\nreaped: {reaped}")
    _show("running / failed AFTER")
