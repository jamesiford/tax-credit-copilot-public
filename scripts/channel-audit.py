"""Print one user's channel audit timeline. [CH-03]

    python scripts/channel-audit.py --user <oid|name> [--since 2026-11-01] [--until ...] [--tool <name>] [--limit 200] [--detail]

Reads whichever store `CHANNEL_STORE` selects (SQLite locally, the Warehouse when
deployed). `--user` is an Entra object id; a name is resolved against the writer
allow-list's display names, which is the only place the platform holds one.

A request with a `begin` and no `end` is shown as PENDING — a crash, or one still
running — rather than dropped.

Exit codes: 0 ok · 2 usage (unknown user, bad date).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

import sql_common as common

_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def resolve_user(text: str, writers) -> str | None:
    """The writer whose display name matches, else the text itself if it is an id.

    An id is anything with no whitespace (Entra object ids are GUIDs, but a test
    tenant's need not be); a name with a space that matches nobody is unknown.
    """
    matches = [g.user_oid for g in writers.live() if (g.display_name or "").lower() == text.lower()]
    if len(matches) == 1:
        return matches[0]
    return text if _GUID.match(text) or not any(ch.isspace() for ch in text) else None


def render_timeline(entries: list[dict]) -> str:
    """One line per request, newest first. PENDING is upper-case on purpose."""
    if not entries:
        return "(no channel activity)"
    lines = []
    for e in entries:
        outcome = "PENDING" if e["outcome"] == "pending" else e["outcome"]
        scope = f"client {e['client_id']}" if e["client_id"] is not None else "no client"
        year = f" TY{e['tax_year']}" if e["tax_year"] is not None else ""
        lines.append(f"{e['begun_at']}  {outcome:<18} {e['action_kind']:<13} {e['tool_name']:<20} {scope}{year}")
    return "\n".join(lines)


def render_detail(entries: list) -> str:
    """The same timeline with what the platform recorded about WHO asked and by what channel."""
    if not entries:
        return "(no channel activity)"
    lines = []
    for entry in entries:
        e = entry.last
        who = f"{e.user_oid} ({e.user_display_name or '(name not provided)'})"
        lines.append(
            f"{entry.begun_at.isoformat()}  {entry.outcome:<10} {e.action_kind:<13} {e.tool_name:<22} "
            f"channel={e.channel} user={who} assurance={e.identity_assurance} guard={e.numeric_guard} "
            f"correlation={e.correlation_id}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, repository=None, writers=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", required=True)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--tool")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--detail", action="store_true", help="also show channel, display name, assurance, guard and correlation id")
    args = parser.parse_args(argv)

    common.load_env()
    from application.wiring import get_channel_audit_repository, get_writer_repository
    from domain.channel import collapse

    repository = repository or get_channel_audit_repository()
    oid = resolve_user(args.user, writers or get_writer_repository())
    if oid is None:
        print(f"unknown user {args.user!r}: pass an Entra object id", file=sys.stderr)
        return common.EXIT_USAGE
    try:
        since, until = _when(args.since), _when(args.until)
    except ValueError as exc:
        print(f"bad date: {exc}", file=sys.stderr)
        return common.EXIT_USAGE

    events = repository.for_user(oid, since=since, until=until, tool=args.tool, limit=args.limit)
    entries = collapse(events)
    print(render_detail(entries) if args.detail else render_timeline([e.to_dict() for e in entries]))
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
