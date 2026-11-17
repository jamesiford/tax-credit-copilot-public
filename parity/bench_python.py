"""Micro-benchmark of the Python engine on the datasets the C# benchmark uses (numbers only).

Loads the ``csv`` dataset from the goldens (the committed synthetic CSV, 9,477 rows) and a generated
large set (that dataset replicated K times with distinct employee ids), then times both methods
(minimum and median of several repetitions, wall clock, single thread).

Usage: python parity/bench_python.py [--large-copies 20] [--reps 5]
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_io  # noqa: E402
from domain.calculation.onezero import run_min_max_method, run_pay_period_method  # noqa: E402


def load_csv_rows() -> list[dict]:
    with gzip.open(Path(__file__).resolve().parent / "goldens" / "datasets.jsonl.gz", "rt") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("name") == "csv":
                return d["rows"]
    raise SystemExit("dataset 'csv' not found")


def replicate(rows: list[dict], copies: int) -> list[dict]:
    out = []
    for k in range(copies):
        for r in rows:
            out.append({**r, "Employee_ID": f"{r['Employee_ID']}-{k}"})
    return out


def time_it(fn, reps: int) -> tuple[float, float]:
    samples = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t)
    return min(samples), statistics.median(samples)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--large-copies", type=int, default=20)
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    pack = engine_io.build_pack({"min_weekly_hours": 35.0, "min_weekly_wages": 680.0, "citation": "bench"})
    small = load_csv_rows()
    large = replicate(small, a.large_copies)
    for name, rows in (("synthetic 9,477 rows", small), (f"generated {len(rows := large):,} rows", large)):
        for label, fn in (("pay_period", run_pay_period_method), ("min_max", run_min_max_method)):
            lo, med = time_it(lambda: fn(rows, tax_year=2025, analysis_start_month=date(2025, 1, 1), pack=pack), a.reps)
            print(f"python {name:>24} {label:>10}: min {lo * 1000:9.1f} ms  median {med * 1000:9.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
