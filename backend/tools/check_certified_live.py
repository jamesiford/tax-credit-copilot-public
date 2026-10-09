"""Do the certified figures still hold on the LIVE run for client 1001?

10,236 employees / 539 Min-Max / 656 Pay Period.

`employee_eligibility` has no `is_current`, so a count without a run filter sums
every run and returns a multiple of the right answer. The live run is the one
`success` manifest that has not been superseded.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from infrastructure.persistence.fabric_warehouse import (  # noqa: E402
    GOLD_SCHEMA,
    OPS_SCHEMA,
    FabricWarehouseConnection,
)

CLIENT = 1001
EXPECTED = {"employees": 10236, "min_max": 539, "pay_period": 656}

with FabricWarehouseConnection().scope() as conn:
    cur = conn.cursor()

    cur.execute(
        f"SELECT TOP 1 run_id, tax_year FROM {OPS_SCHEMA}.run_manifest "
        f"WHERE client_id = ? AND run_status = 'success' "
        f"AND superseded_by_run_id IS NULL AND run_completed_at IS NOT NULL "
        f"ORDER BY run_started_at DESC", [CLIENT],
    )
    run_id, tax_year = cur.fetchone()
    print(f"live run: {run_id}  TY{tax_year}")

    cur.execute(
        f"SELECT COUNT(DISTINCT employee_id) FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE run_id = ?", [run_id],
    )
    employees = cur.fetchone()[0]

    counts = {}
    for method in ("min_max", "pay_period"):
        cur.execute(
            f"SELECT COUNT(DISTINCT employee_id) FROM {GOLD_SCHEMA}.employee_eligibility "
            f"WHERE run_id = ? AND method = ? AND eligible = 1", [run_id, method],
        )
        counts[method] = cur.fetchone()[0]

    actual = {"employees": employees, **counts}
    print("\n            expected   actual")
    ok = True
    for key, want in EXPECTED.items():
        got = actual[key]
        flag = "OK " if got == want else "!! "
        ok &= got == want
        print(f"  {flag}{key:<12}{want:>7}{got:>9}")

    print("\nCERTIFIED FIGURES REPRODUCE" if ok else "\nFIGURES MOVED - this is a finding, not something to absorb")

    print("\n-- sanity: unfiltered count sums every run")
    cur.execute(
        f"SELECT COUNT(DISTINCT employee_id) FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ?", [CLIENT],
    )
    print("   distinct employees across ALL runs:", cur.fetchone()[0])
    cur.execute(
        f"SELECT COUNT(*) FROM {GOLD_SCHEMA}.employee_eligibility "
        f"WHERE client_id = ? AND method = 'min_max' AND eligible = 1", [CLIENT],
    )
    print("   min_max eligible rows across ALL runs:", cur.fetchone()[0])
