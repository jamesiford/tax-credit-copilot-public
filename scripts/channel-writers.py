"""Manage the channel writer allow-list. [CH-04]

    python scripts/channel-writers.py add <oid> [--name "Display Name"] [--by <who>]
    python scripts/channel-writers.py remove <oid>
    python scripts/channel-writers.py list

The allow-list is `tcc_ops.channel_user`; `CHANNEL_WRITER_SOURCE` says whether the
API consults it (`allowlist`, `either`). Removal stamps `removed_at` rather than
deleting the row, so who held the right, and when, stays answerable. Adding
someone already listed is a no-op, not an error: running it twice must be safe.

Exit codes: 0 ok · 2 usage (bad object id, nobody to remove).
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys

import sql_common as common

_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def render(grants) -> str:
    if not grants:
        return "(no writers)"
    rows = sorted(grants, key=lambda g: g.added_at)
    return "\n".join(
        f"{g.user_oid}  {(g.display_name or '-'):<28} added {g.added_at:%Y-%m-%d} by {g.added_by}"
        for g in rows
    )


def main(argv: list[str] | None = None, *, writers=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("oid")
    add.add_argument("--name")
    add.add_argument("--by", default=None, help="who is granting; defaults to the operating-system user")
    sub.add_parser("remove").add_argument("oid")
    sub.add_parser("list")
    args = parser.parse_args(argv)

    common.load_env()
    if writers is None:
        from application.wiring import get_writer_repository

        writers = get_writer_repository()
    from domain.channel import WriterGrant

    if args.command == "list":
        print(render(writers.live()))
        return common.EXIT_OK
    if not _GUID.match(args.oid):
        print(f"{args.oid!r} is not an Entra object id (a GUID)", file=sys.stderr)
        return common.EXIT_USAGE
    if args.command == "add":
        if writers.is_writer(args.oid):
            print(f"{args.oid} is already a writer")
            return common.EXIT_OK
        writers.grant(WriterGrant(user_oid=args.oid, added_by=args.by or getpass.getuser(), display_name=args.name))
        print(f"added {args.oid}")
        return common.EXIT_OK
    if not writers.revoke(args.oid):
        print(f"{args.oid} is not a current writer", file=sys.stderr)
        return common.EXIT_USAGE
    print(f"removed {args.oid}")
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
