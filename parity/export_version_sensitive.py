"""Version-sensitive facts: the primitive vectors whose expected output differs between CPython 3.12 and 3.14.

The oracle is 3.12 (see ``oracle.py``); this file keeps what 3.14 would answer as DATA so that an interpreter upgrade
is a deliberate, visible step rather than a silent drift. It runs the primitives exporter under a second interpreter
(``--py314``) with the exploratory flag, pairs the vectors by position (same seed, so identical inputs) and writes
``parity/goldens/version-sensitive.jsonl.gz``: one line per differing vector,

    {"k": "vs", "kind": <vector kind>, "index": <position>, "py312": <vector>, "py314": <vector>}

preceded by a meta line recording both interpreters. Runs only on 3.12.

Usage: python parity/export_version_sensitive.py --py314 PATH_TO_PYTHON_3_14 [--out FILE] [--check]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_primitives  # noqa: E402
import oracle  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "version-sensitive.jsonl.gz"


def _vectors(data: bytes) -> list[dict]:
    return [json.loads(line) for line in gzip.decompress(data).decode("ascii").splitlines()]


def _input_of(v: dict) -> dict:
    """The part of a vector that is the question rather than the answer (identical across interpreters)."""
    return {k: x for k, x in v.items() if k in {"k", "xs", "s", "a", "b"}}


def build(py314: str, seed: int) -> bytes:
    new = _vectors(export_primitives.build(seed))
    with tempfile.TemporaryDirectory() as tmp:
        other = Path(tmp) / "primitives314.jsonl.gz"
        subprocess.run([py314, str(Path(__file__).resolve().parent / "export_primitives.py"), oracle.FLAG, "--seed", str(seed),
                        "--out", str(other)], check=True, capture_output=True)
        old = _vectors(other.read_bytes())
    if len(new) != len(old):
        raise SystemExit(f"vector counts differ: {len(new)} vs {len(old)}")
    lines = [json.dumps({"k": "meta", "python": new[0]["python"], "py314": old[0]["python"], "seed": seed}, separators=(",", ":"))]
    differing = 0
    for i, (a, b) in enumerate(zip(new[1:], old[1:], strict=True), start=1):
        if a == b:
            continue
        if a["k"] != b["k"] or _input_of(a) != _input_of(b):
            raise SystemExit(f"vector {i}: inputs differ between interpreters ({a['k']}); the pairing is invalid")
        differing += 1
        lines.append(json.dumps({"k": "vs", "kind": a["k"], "index": i, "py312": a, "py314": b}, separators=(",", ":"), ensure_ascii=True))
    print(f"{differing} version-sensitive vectors of {len(new) - 1}", file=sys.stderr)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        for line in lines:
            gz.write(line.encode("ascii") + b"\n")
    return buf.getvalue()


def main() -> int:
    oracle.require()
    ap = argparse.ArgumentParser()
    ap.add_argument("--py314", required=True, help="path to the later interpreter to compare against")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=export_primitives.SEED)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    data = build(a.py314, a.seed)
    if a.check:
        return 0 if a.out.exists() and a.out.read_bytes() == data else 1
    a.out.write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
