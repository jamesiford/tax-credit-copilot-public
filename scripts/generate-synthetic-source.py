#!/usr/bin/env python
"""Generate a synthetic source lakehouse at scale: N accounts, M payroll rows, a realistic skew. [05.6]

    python scripts/generate-synthetic-source.py --root DIR --accounts 200 --rows 5000000 [--seed 7] [--mapping-file F]
    python scripts/generate-synthetic-source.py --accounts 20 --rows 50000 --dry-run

Deterministic by `--seed`. Account sizes follow a power law (many small accounts, a few very large) and the rows are exact.
Account ids start at 910001 and names are `Scale Account NNNNN`: different from any demo or customer account. Everything is
invented and no table carries a name, date of birth, phone or email. The lakehouse is written in the shape of the source
mapping in force (use `--mapping-file` for an alternate shape) and the app-owned lookups are not generated.

It is a thin wrapper over `scripts/fabric/build-sample-lakehouse.py --source scale`, so a dry run, reconciliation and a
data-quality report come with it. Used by the scale work (prompt 08) and the read-mode spike (prompt 10).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_BUILD = Path(__file__).resolve().parent / "fabric" / "build-sample-lakehouse.py"


def main(argv: list[str] | None = None) -> int:
    spec = importlib.util.spec_from_file_location("build_sample_lakehouse", _BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = list(sys.argv[1:] if argv is None else argv)
    if "--dry-run" in args and "--root" not in args and "--fabric" not in args:
        args += ["--root", "."]  # a dry run writes nothing, so the target is only a label
    return module.main(["--source", "scale", *args])


if __name__ == "__main__":
    raise SystemExit(main())
