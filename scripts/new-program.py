"""Scaffold a program: `python scripts/new-program.py program|year ...`. [ADR-013]

    python scripts/new-program.py program --code XX_JTC --state XX --name "Example Jobs Credit" --slug jtc [--dry-run]
    python scripts/new-program.py year --pack xx_jtc.json --year 2027 [--dry-run]

`program` writes a base pack and a `draft` registry entry; `year` writes `<program>/<year>.draft.json`. Every statutory
value in either is `null` and flagged `_prototype_verify`, so the file fails validation until a person fills it from a cited
source. The year file is a `.draft.json` the engine ignores; renaming it to `<year>.json` after validating it is the human
step that makes the year authored. Nothing here is verified, and nothing activates statute. [ADR-005]

Exit codes: 0 written, 1 refused (already exists, unknown pack), 2 usage.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new program or a year-pack skeleton.")
    sub = parser.add_subparsers(dest="what", required=True)
    prog = sub.add_parser("program", help="a draft registry entry and a base pack skeleton")
    prog.add_argument("--code", required=True, help="credit code, e.g. XX_JTC")
    prog.add_argument("--state", required=True, help="two-letter state code")
    prog.add_argument("--name", required=True)
    prog.add_argument("--slug", required=True, help="pack file suffix: <state>_<slug>.json")
    year = sub.add_parser("year", help="a year-pack skeleton for an existing pack")
    year.add_argument("--pack", required=True, help="base pack file name, e.g. xx_jtc.json")
    year.add_argument("--year", required=True, type=int)
    for p in (prog, year):
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--rules-dir", help="rules folder (default RULES_DIR or backend/rules)")
    args = parser.parse_args(argv)
    if args.rules_dir:
        os.environ["RULES_DIR"] = args.rules_dir
    from domain.programs import RegistryError
    from tools import program_scaffold

    try:
        if args.what == "program":
            wrote = program_scaffold.create_program(args.code.upper(), args.state, args.name, args.slug, dry_run=args.dry_run)
        else:
            wrote = [program_scaffold.create_year(args.pack, args.year, dry_run=args.dry_run)]
    except RegistryError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(("would write: " if args.dry_run else "wrote: ") + ", ".join(wrote))
    return 0


if __name__ == "__main__":
    sys.exit(main())
