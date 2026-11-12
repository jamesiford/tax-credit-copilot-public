#!/usr/bin/env python
"""Spike: the SQL-endpoint payroll read against the OneLake read, on a local lake. [10]

    python scripts/fabric/spike-sql-read.py [--accounts 40 --rows 400000 --seed 1] [--out spike.json]

Builds a synthetic lake with the scale generator, then reads a small, a median and the largest account in each
`SOURCE_READ_MODE` through the reader the app uses, and reports time, peak Python memory, rows read, round trips
and the approximate payload, plus PARITY: the SQL dataset must equal the OneLake dataset, and so must the engine
rows (values AND order).

The SQL endpoint here is EMULATED (`backend/tests/sql_endpoint_fake.py`: SQLite behind the ODBC types). Rows,
statements and parity are properties of this code and are real. Seconds and memory for the SQL mode measure the
emulation, not Fabric: do not read them as the endpoint's speed. That measurement is a live check
(see docs/architecture/SQL-READ-PATH.md). Peak memory is `tracemalloc`'s, which does not see Arrow buffers.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))


def _delta_meter():
    from deltalake import DeltaTable

    calls: list[dict] = []
    original = DeltaTable.to_pyarrow_table

    def counted(table, *args, **kwargs):
        result = original(table, *args, **kwargs)
        calls.append({"rows": result.num_rows, "bytes": result.nbytes})
        return result

    DeltaTable.to_pyarrow_table = counted
    return calls, lambda: setattr(DeltaTable, "to_pyarrow_table", original)


def _read(reader, account: int, mode: str, endpoint, fabric, sql_scan):
    """One cold read of one account in one mode; returns (dataset, engine rows, metrics)."""
    from data.source.to_bcs import source_to_bcs_rows

    os.environ["SOURCE_READ_MODE"] = mode
    fabric.clear_cache()
    endpoint.reset_counters()
    calls, restore = _delta_meter()
    started = time.perf_counter()
    try:
        dataset = reader.for_account(account)
    finally:
        seconds = time.perf_counter() - started
        restore()
    rows = source_to_bcs_rows(dataset)
    counted = {"statements": len(endpoint.statements), "rows": endpoint.rows_sent, "chars": endpoint.payload_chars}
    fabric.clear_cache()
    tracemalloc.start()
    try:
        reader.for_account(account)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        fabric.clear_cache()
    metrics = {
        "mode": mode, "seconds": round(seconds, 3), "peak_python_mb": round(peak / 1e6, 1),
        "rows_read": counted["rows"] if mode == "sql" else sum(c["rows"] for c in calls),
        "round_trips": counted["statements"] if mode == "sql" else len(calls),
        "approx_payload_mb": round(counted["chars"] / 1e6, 2) if mode == "sql" else round(sum(c["bytes"] for c in calls) / 1e6, 2),
    }
    return dataset, rows, metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accounts", type=int, default=40)
    parser.add_argument("--rows", type=int, default=400_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", help="write the report as JSON")
    args = parser.parse_args(argv)

    os.environ.setdefault("PAY_CODE_POLICY", "assume")
    from local_lakehouse import use_local_lakehouse
    from sql_endpoint_fake import FakeLakehouseSql

    from data.source import build_lake, from_fabric, sql_scan
    from data.source.scale import generate

    class _Patch:
        """`use_local_lakehouse` wants a pytest monkeypatch; this is the small part of it the helper uses."""

        def setattr(self, target, name, value):
            setattr(target, name, value)

    root = Path(tempfile.mkdtemp(prefix="tcc-sqlspike-"))
    datasets = generate(args.accounts, args.rows, args.seed)
    build_lake.build_local(datasets, root, schema="tcc_source")
    use_local_lakehouse(_Patch(), root)
    endpoint = FakeLakehouseSql(root, schema="tcc_source")
    sql_scan._connection = lambda: endpoint
    reader = from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="tcc_source")

    sizes = sorted((len(d.payroll), d.account.account_id) for d in datasets)
    picks = {"small": sizes[0], "median": sizes[len(sizes) // 2], "large": sizes[-1]}
    report: dict = {"accounts": args.accounts, "payroll_rows_total": args.rows, "scenarios": []}
    for label, (payroll_rows, account) in picks.items():
        one_ds, one_rows, one = _read(reader, account, "onelake", endpoint, from_fabric, sql_scan)
        sql_ds, sql_rows, sql = _read(reader, account, "sql", endpoint, from_fabric, sql_scan)
        report["scenarios"].append({
            "scenario": label, "account_payroll_rows": payroll_rows,
            "onelake": one, "sql": sql,
            "dataset_parity": dataclasses.asdict(one_ds) == dataclasses.asdict(sql_ds),
            "engine_rows_parity_values_and_order": one_rows == sql_rows,
        })
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if all(s["dataset_parity"] and s["engine_rows_parity_values_and_order"] for s in report["scenarios"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
