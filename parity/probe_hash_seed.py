"""Probe: does engine output depend on Python's per-process string hash seed?

The Pay Period method sums weeks over a *set* of (PPS, PPE) tuples, so iteration
order depends on hash randomisation. This runs the engine on the synthetic CSV and
prints a digest; run it under several PYTHONHASHSEED values and compare.
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_io as io  # noqa: E402
import oracle  # noqa: E402

oracle.require()

rows = list(csv.DictReader(open(Path(__file__).resolve().parents[1] / "backend" / "data" / "payroll_pay_periods.csv", encoding="utf-8")))
pack = {"min_weekly_hours": 35.0, "min_weekly_wages": 636.0, "included_pay_codes": None, "excluded_pay_codes": None}
digests = []
for op in ("pay_period", "min_max"):
    for ty, start in ((2024, "2024-01-01"), (2023, "2023-01-01"), (2025, "2025-01-01")):
        req = {"id": "x", "op": op, "rows": rows, "params": {"tax_year": ty, "analysis_start_month": start, "pack": pack, "with_trail": True}}
        resp = io.execute(req)
        digests.append(resp.get("float_digest") or resp.get("error"))
        digests.append(hashlib.sha256(io.dumps(resp).encode()).hexdigest()[:16])
print(hashlib.sha256("|".join(map(str, digests)).encode()).hexdigest()[:24], len(rows))
