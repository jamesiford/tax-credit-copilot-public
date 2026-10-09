"""Delete claims a test run leaked into the operational store.

One-shot. `test_run_client_calculation` stubbed the Gold writer but not the
claim repository, so every run recorded account 1001 at TY2024 and TY2025 from
the synthetic CSV fixture — and the portfolio page read them back as that
client's credit position. The test is fixed; this clears what it already wrote.

Direct SQL on purpose. `ClaimRepository` has no `delete`: it is append-only with
a `history`, which is right for a record that lands on a filed return. Widening
that port so a cleanup script can use it would put a delete on the audit trail
for the sake of dev junk.

    $env:PYTHONPATH="."; python tools/purge_test_claims.py          # report
    $env:PYTHONPATH="."; python tools/purge_test_claims.py --run    # delete
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

LEAKED_ACTOR = "tests"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="delete rather than report")
    args = parser.parse_args()

    store = os.getenv("CLAIM_STORE", "sqlite").strip().lower()
    if store != "sqlite":
        print(
            f"CLAIM_STORE={store!r}. This only touches the local SQLite store; a "
            f"deployed environment should never have had a test write to it.",
            file=sys.stderr,
        )
        return 2

    from infrastructure.persistence.sqlite_claims import _DEFAULT_PATH

    path = Path(os.getenv("OPERATIONAL_DB", _DEFAULT_PATH))
    if not path.exists():
        print(f"No operational store at {path}. Nothing to do.")
        return 0

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT client_id, program_code, tax_year, identified_usd, average_headcount "
            "FROM program_claim WHERE decided_by = ?",
            (LEAKED_ACTOR,),
        ).fetchall()

        if not rows:
            print(f"{path}: no claims recorded by the test suite. Nothing to do.")
            return 0

        print(f"{path}")
        for row in rows:
            print(
                f"  client={row['client_id']} {row['program_code']} TY{row['tax_year']} "
                f"identified={row['identified_usd']} avg={row['average_headcount']}"
            )

        if not args.run:
            print(f"\n{len(rows)} row(s) would be deleted. Re-run with --run.")
            return 0

        with conn:
            conn.execute("DELETE FROM program_claim WHERE decided_by = ?", (LEAKED_ACTOR,))
        print(f"\nDeleted {len(rows)} row(s).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
