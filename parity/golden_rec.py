"""Shared recorder for the stage-DS5 exporters (``export_performance.py`` and ``export_models.py``).

Line format (JSONL, gzip, mtime 0), as in ``export_claims.py``: ``{"k":"call","id":n,"fn":name,"out":tree,"args":{...}}`` or
``{"k":"call",...,"err":"TypeName","msg":str(exception)}``. Tagged values (see ``enc``): ``{"$date": iso}``,
``{"$dt": iso}``, ``{"$dec": str}``; floats keep their ``repr`` (non-finite as ``NaN``/``Infinity``), ints stay ints.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable


def enc(x):
    """JSON-able view of an argument or an output tree."""
    if isinstance(x, datetime):
        return {"$dt": x.isoformat()}
    if isinstance(x, date):
        return {"$date": x.isoformat()}
    if isinstance(x, Decimal):
        return {"$dec": str(x)}
    if isinstance(x, Enum):
        return x.value
    if is_dataclass(x) and not isinstance(x, type):
        return {f.name: enc(getattr(x, f.name)) for f in fields(x)}
    if isinstance(x, dict):
        return {k: enc(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [enc(v) for v in x]
    return x


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


class Recorder:
    """Collects calls; ``run`` is a zero-argument closure over the production function."""

    def __init__(self) -> None:
        self.lines: list = []
        self.counts: dict[str, int] = {}
        self.errors = 0

    def call(self, fn: str, args: dict, run: Callable[[], object]) -> None:
        text_in = dumps(enc(args))
        try:
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "out": enc(run())}
        except Exception as e:  # the exception type and message are part of the contract
            self.errors += 1
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "err": type(e).__name__, "msg": str(e)}
        self.counts[fn] = self.counts.get(fn, 0) + 1
        self.lines.append((text_in, rec))


def serialise(rec: Recorder, meta_extra: dict, seed: int, stamp: dict) -> bytes:
    meta = {"k": "meta", "seed": seed, "calls": len(rec.lines), "errors": rec.errors, "counts": rec.counts, **meta_extra, **stamp}
    lines = [dumps(meta)]
    for text_in, rec_line in rec.lines:
        body = dumps(rec_line)
        lines.append(body[:-1] + ',"args":' + text_in + "}")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(("\n".join(lines) + "\n").encode("ascii"))
    return buf.getvalue()


def main(name: str, default_out: Path, default_seed: int, build: Callable[[int], bytes]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--seed", type=int, default=default_seed)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = build(args.seed)
    if args.check:
        ok = args.out.exists() and args.out.read_bytes() == data
        print(f"{name} golden is current" if ok else f"STALE {name} golden", file=__import__("sys").stderr)
        return 0 if ok else 1
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0
