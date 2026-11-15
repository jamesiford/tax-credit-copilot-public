"""Golden exporter: runs the production engine over the scenario matrix and writes the fixtures.

Outputs (all deterministic, gzip mtime fixed):
  parity/goldens/datasets.jsonl.gz   {"name", "rows"}            one line per dataset
  parity/goldens/engine.jsonl.gz     {"id", "op", "dataset"?, "rows"?, "params", "expected"}   expected = engine_io response

``--check`` regenerates in memory and fails (exit 1) when the committed goldens differ, so a Python
engine change forces regeneration. Only new files under parity/ are written.

Usage: python parity/export_goldens.py [--check] [--out DIR]
"""
from __future__ import annotations

import argparse
import gzip
import io as _io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_io  # noqa: E402
import matrix  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "goldens"


def _gz(lines: list[str]) -> bytes:
    buf = _io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        for line in lines:
            gz.write(line.encode("ascii") + b"\n")
    return buf.getvalue()


def build() -> dict[str, bytes]:
    started = time.time()
    datasets, scenarios = matrix.build()
    ds_lines = [engine_io.dumps({"k": "meta", "python": sys.version.split()[0], "datasets": len(datasets)})]
    ds_lines += [engine_io.dumps({"name": n, "rows": r}) for n, r in datasets.items()]
    eng_lines = [engine_io.dumps({"k": "meta", "python": sys.version.split()[0], "scenarios": len(scenarios)})]
    ok = err = 0
    for s in scenarios:
        req = dict(s)
        if "dataset" in s:
            req["rows"] = datasets[s["dataset"]]
        resp = engine_io.execute(req)
        if resp["ok"]:
            ok += 1
        else:
            err += 1
        eng_lines.append(engine_io.dumps({**s, "expected": resp}))
    print(f"{len(scenarios)} scenarios ({ok} ok, {err} errors), {len(datasets)} datasets, {time.time() - started:.1f}s", file=sys.stderr)
    return {"datasets.jsonl.gz": _gz(ds_lines), "engine.jsonl.gz": _gz(eng_lines)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args()
    files = build()
    if a.check:
        stale = [n for n, b in files.items() if not (a.out / n).exists() or (a.out / n).read_bytes() != b]
        if stale:
            print("STALE goldens (engine or matrix changed): " + ", ".join(stale), file=sys.stderr)
            return 1
        print("goldens are current", file=sys.stderr)
        return 0
    a.out.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (a.out / n).write_bytes(b)
        print(f"{n}: {len(b) / 1e6:.2f} MB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
