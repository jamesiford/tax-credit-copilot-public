"""Engine CLI: the production engine behind a JSON Lines pipe, for the C# differential fuzzer.

Reads one request per line on stdin (schema in ``engine_io``) and writes one response per line on
stdout, flushing after each so a caller can run a persistent session. Each process gets its own
string-hash seed (Python's default), which makes a fuzz run double as a test that the engine does
not depend on set iteration order.

Usage: python parity/engine_cli.py            (run from the backend directory or anywhere)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_io  # noqa: E402
import oracle  # noqa: E402


def main() -> int:
    oracle.require()
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("op") == "call":
                import fuzz_ops  # family operations; imported lazily, see its docstring for the schema

                out.write(fuzz_ops.respond(req) + "\n")
                out.flush()
                continue
            resp = engine_io.execute(req)
            text = engine_io.dumps(resp)
        except (ValueError, TypeError, OverflowError):
            # allow_nan=False rejects a NaN/Infinity result: report it rather than emit invalid JSON.
            text = engine_io.dumps({"id": None, "ok": False, "error": "NonFiniteResult"})
        out.write(text + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
