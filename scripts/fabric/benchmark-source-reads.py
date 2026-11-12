#!/usr/bin/env python
"""Benchmark the source reads on a local lake: time, peak memory, rows and bytes read, per scenario. [08.8]

    python scripts/fabric/benchmark-source-reads.py [--accounts 40 --rows 400000 --seed 1] [--root DIR] [--out report.json]

Builds (or reuses) a synthetic lake with the scale generator, then measures three scenarios through the same reader the app
uses (`FabricLakehouseReader`, over local Delta tables, no network):

  small_account     the smallest account's full dataset
  large_account     the largest account's full dataset
  portfolio_view    the client book (what the portfolio page needs of the source) - it must read no payroll

Rows and bytes are counted at the Delta boundary (every `to_pyarrow_table` call), independently of the app's own counters,
so the same harness measures the code before and after a change. Peak memory is Python's `tracemalloc` peak (it does not see
Arrow buffers; it is for comparison between runs on the same machine, not an absolute figure). Targets are PROPOSED in the
session report, not asserted here.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


class Meter:
    """Counts rows, bytes and calls per table at the Delta boundary."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def install(self) -> None:
        from deltalake import DeltaTable

        original = DeltaTable.to_pyarrow_table
        meter = self

        def counted(table, *args, **kwargs):
            result = original(table, *args, **kwargs)
            meter.calls.append({"table": Path(str(table.table_uri)).name, "rows": result.num_rows, "bytes": result.nbytes,
                                "columns": result.num_columns, "filtered": bool(kwargs.get("filters"))})
            return result

        DeltaTable.to_pyarrow_table = counted
        self._restore = lambda: setattr(DeltaTable, "to_pyarrow_table", original)

    def restore(self) -> None:
        self._restore()

    def summary(self) -> dict:
        per: dict[str, dict] = {}
        for c in self.calls:
            t = per.setdefault(c["table"], {"calls": 0, "rows": 0, "bytes": 0, "unfiltered_calls": 0})
            t["calls"] += 1
            t["rows"] += c["rows"]
            t["bytes"] += c["bytes"]
            t["unfiltered_calls"] += 0 if c["filtered"] else 1
        return {"tables": per, "rows": sum(c["rows"] for c in self.calls), "bytes": sum(c["bytes"] for c in self.calls)}


def measure(label: str, work) -> dict:
    """Two passes of the same work: one timed with nothing else running, one under `tracemalloc` (which slows it a lot)."""
    meter = Meter()
    meter.install()
    started = time.perf_counter()
    try:
        value = work()
    finally:
        seconds = time.perf_counter() - started
        meter.restore()
    tracemalloc.start()
    try:
        work()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"scenario": label, "seconds": round(seconds, 3), "peak_python_mb": round(peak / 1e6, 1), "result": value, **meter.summary()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accounts", type=int, default=40)
    parser.add_argument("--rows", type=int, default=400_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--root", help="reuse (or create) a lake here instead of a temporary one")
    parser.add_argument("--out", help="write the report as JSON")
    parser.add_argument("--label", default="run")
    args = parser.parse_args(argv)

    import tempfile

    from data.source import build_lake, from_fabric
    from data.source.scale import generate

    root = Path(args.root) if args.root else Path(tempfile.mkdtemp(prefix="tcc-bench-"))
    datasets = generate(args.accounts, args.rows, args.seed)
    if not (root / "Tables").exists():
        build_lake.build_local(datasets, root, schema="tcc_source")

    from data.source import onelake

    def local(table, *, workspace, lakehouse, schema):
        return str(root / "Tables" / onelake.table_uri(table, workspace=workspace, lakehouse=lakehouse, schema=schema).split("/Tables/", 1)[1])

    from_fabric.table_uri = local
    from_fabric.FabricLakehouseReader._storage_options = lambda self: {}
    reader = from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="tcc_source")

    sizes = sorted(((len(d.payroll), d.account.account_id) for d in datasets))
    (small_rows, small_id), (large_rows, large_id) = sizes[0], sizes[-1]

    def fresh(work):
        def run():
            from_fabric.clear_cache()
            return work()

        return run

    results = [
        measure("small_account", fresh(lambda: len(reader.bcs_rows(small_id)))),
        measure("large_account", fresh(lambda: len(reader.bcs_rows(large_id)))),
        measure("portfolio_view", fresh(lambda: len(reader.list_accounts()))),
        measure("unknown_account_twice", fresh(lambda: (reader.for_account(1), reader.for_account(1)) and 0)),
    ]
    report = {"label": args.label, "accounts": args.accounts, "payroll_rows_total": args.rows,
              "small_account_rows": small_rows, "large_account_rows": large_rows, "scenarios": results}
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
