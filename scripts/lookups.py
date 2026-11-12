#!/usr/bin/env python
"""Author and inspect the app-owned lookups (the override layer). [07]

    python scripts/lookups.py list [--account ID]
    python scripts/lookups.py show   <lookup> [--account ID | --global]
    python scripts/lookups.py import <lookup> (--account ID | --global) FILE --by WHO [--basis TEXT] [--inferred] [--dry-run]
    python scripts/lookups.py export <lookup> (--account ID | --global) [--out FILE]
    python scripts/lookups.py diff   <lookup> (--account ID | --global) FILE
    python scripts/lookups.py audit  [<lookup>]

Lookups that can be overridden: pay_code_category (statute-affecting: which pay counts), entity_fiscal_year_rules
(statute-affecting: the client's fiscal window). Every write appends an audit row. Needs LOOKUP_STORE=sqlite (local) or
warehouse; with `none` the commands that read still run and the ones that write refuse and say what to set. Nothing is
ever written to the customer's lakehouse.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "show", "import", "export", "diff", "audit"):
        p = sub.add_parser(name)
        if name in ("show", "import", "export", "diff", "audit"):
            p.add_argument("lookup", nargs="?" if name == "audit" else None)
        p.add_argument("--account", type=int)
        p.add_argument("--global", dest="global_", action="store_true")
        if name in ("import", "diff"):
            p.add_argument("file")
        if name == "import":
            p.add_argument("--by", required=True, help="who is authoring this (recorded)")
            p.add_argument("--basis", default="", help="why; recorded")
            p.add_argument("--inferred", action="store_true", help="a convention, not something the data owner told us")
            p.add_argument("--dry-run", action="store_true")
        if name == "export":
            p.add_argument("--out")
    return parser


def _entries(store, lookup: str, client_id: int):
    return [e for e in store.entries(lookup, client_id) if e.client_id == client_id]


def run(args: argparse.Namespace) -> int:
    import bootstrap.source_binding  # noqa: F401 - installs the lookup store the settings choose
    from data.lookups import admin, lookup_status
    from data.lookups.store import get_store

    store = get_store()
    if args.command == "list":
        for row in lookup_status(account_id=args.account):
            flag = " [statute-affecting]" if row["statute_affecting"] else ""
            print(f"{row['lookup']:<26} {row['status']:<28} {row['affects']}{flag}")
            if row.get("if_missing"):
                print(f"{'':<26} if missing: {row['if_missing']}")
        return 0
    if args.command == "audit":
        for row in store.audit(args.lookup):
            print(json.dumps(row, default=str))
        return 0
    client_id = admin.scope(args.account, args.global_ or (args.command == "show" and args.account is None))
    if args.command == "show":
        for e in _entries(store, args.lookup, client_id):
            print(f"{e.key_kind:<9} {e.key:<24} {e.value}  [{e.authored_by}{', inferred' if e.inferred else ''}]")
        return 0
    if args.command == "export":
        text = admin.to_text(args.lookup, _entries(store, args.lookup, client_id))
        Path(args.out).write_text(text, encoding="utf-8") if args.out else print(text, end="")
        return 0
    proposed = admin.parse_file(args.lookup, Path(args.file).read_text(encoding="utf-8"), client_id=client_id,
                                actor=getattr(args, "by", "cli"), basis=getattr(args, "basis", ""), inferred=getattr(args, "inferred", False))
    delta = admin.diff(_entries(store, args.lookup, client_id), proposed)
    print(f"added {len(delta['added'])}, changed {len(delta['changed'])}, unchanged {len(delta['unchanged'])}, untouched {len(delta['untouched'])}")
    for old, new in delta["changed"]:
        print(f"  {new.key_kind} {new.key}: {old.value} -> {new.value}")
    if args.command == "import" and not args.dry_run:
        for entry in [*delta["added"], *(new for _, new in delta["changed"])]:
            store.put(entry)
        print("written; every change is in the audit trail")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 - the operator needs the reason, not a trace
        print(f"lookups: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
