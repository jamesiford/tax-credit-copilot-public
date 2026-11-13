"""Validate rule packs: `python scripts/validate-rule-pack.py <path> | --all [--json] [--rules-dir DIR]`. [ADR-013]

Checks the JSON Schema and the semantic rules (supported models, naming, unique credit codes, no inheritance between
years, thresholds, verified claims) and reports `_prototype_verify` flags. A pass means well-formed and consistent,
never that a value is legally correct.

Exit codes: 0 every file valid, 1 at least one error, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))


def _human(reports) -> str:
    lines = []
    for r in reports:
        status = "ok" if r.ok else "INVALID"
        lines.append(f"{status:8} {r.kind:5} {r.file}")
        lines.extend(f"    {i.severity:7} {i.code}: {i.path or '-'}: {i.message}" for i in r.issues if i.severity != "info")
        flags = sum(1 for i in r.issues if i.code == "unverified")
        if flags:
            lines.append(f"    info    {flags} _prototype_verify flag(s): not verified")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate rule packs.")
    parser.add_argument("path", nargs="?", help="a base pack or year pack file")
    parser.add_argument("--all", action="store_true", help="every pack under the rules folder")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--rules-dir", help="rules folder (default RULES_DIR or backend/rules)")
    args = parser.parse_args(argv)
    if bool(args.path) == bool(args.all):
        parser.print_usage(sys.stderr)
        return 2
    if args.rules_dir:
        os.environ["RULES_DIR"] = args.rules_dir
    from tools.pack_validation import validate_all, validate_pack

    reports = validate_all() if args.all else [validate_pack(Path(args.path))]
    if args.json:
        print(json.dumps([{"file": r.file, "kind": r.kind, "ok": r.ok, "issues": [i.__dict__ for i in r.issues]} for r in reports], indent=2))
    else:
        print(_human(reports))
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
