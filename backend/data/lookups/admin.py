"""Authoring helpers for the lookup CLI: read a file into override entries, export entries, diff two sets. [07]

Pure functions over `OverrideEntry`, so the CLI is thin and the behaviour is testable without a store or a terminal.
`pay_code_category` files are CSV (`kind,key,value`, kind `code` or `category`) or a JSON object of code to canonical
category; `entity_fiscal_year_rules` files are a JSON object keyed by entity id (or `default`) whose values carry
`fiscal_year_begin`, `fiscal_year_end` and optionally `rule_expression`.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date

from .store import GLOBAL_CLIENT, OverrideEntry

LOOKUPS = ("pay_code_category", "entity_fiscal_year_rules")


class AdminError(ValueError):
    """A file that cannot be turned into overrides; the message says what to fix."""


def _entry(lookup: str, client_id: int, kind: str, key: str, value: str, actor: str, basis: str, inferred: bool) -> OverrideEntry:
    return OverrideEntry(lookup, client_id, kind, key, value, actor, basis, inferred)


def _pay_code_rows(text: str) -> list[tuple[str, str, str]]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        data = json.loads(text)
        return [("code", str(k).strip().upper(), str(v)) for k, v in (data.get("entries") or data).items()]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or {"kind", "key", "value"} - set(reader.fieldnames):
        raise AdminError("a pay-code CSV needs the header kind,key,value (kind is `code` or `category`)")
    rows = []
    for row in reader:
        kind = (row["kind"] or "").strip().lower()
        if kind not in ("code", "category"):
            raise AdminError(f"kind must be `code` or `category`, not {kind!r}")
        key = row["key"].strip().upper() if kind == "code" else row["key"].strip()
        rows.append((kind, key, row["value"].strip()))
    return rows


def _fiscal_rows(text: str) -> list[tuple[str, str, str]]:
    out = []
    for key, rule in json.loads(text).items():
        missing = [k for k in ("fiscal_year_begin", "fiscal_year_end") if k not in rule]
        if missing:
            raise AdminError(f"rule {key!r} lacks {', '.join(missing)}")
        date.fromisoformat(rule["fiscal_year_begin"]), date.fromisoformat(rule["fiscal_year_end"])
        out.append(("rule", str(key), json.dumps(rule, sort_keys=True)))
    return out


def parse_file(lookup: str, text: str, *, client_id: int, actor: str, basis: str = "", inferred: bool = False) -> list[OverrideEntry]:
    """Override entries from a file's text; an unknown lookup or a malformed file is an `AdminError`."""
    if lookup not in LOOKUPS:
        raise AdminError(f"{lookup!r} cannot be overridden; one of {', '.join(LOOKUPS)}")
    try:
        rows = _pay_code_rows(text) if lookup == "pay_code_category" else _fiscal_rows(text)
    except (ValueError, KeyError, AttributeError) as exc:
        raise AdminError(f"cannot read the {lookup} file: {exc}") from exc
    if not rows:
        raise AdminError("the file holds no entries")
    return [_entry(lookup, client_id, kind, key, value, actor, basis, inferred) for kind, key, value in rows]


def to_text(lookup: str, entries: list[OverrideEntry]) -> str:
    """The inverse of `parse_file` for the rows given (CSV for pay codes, JSON for fiscal rules)."""
    if lookup == "entity_fiscal_year_rules":
        return json.dumps({e.key: json.loads(e.value) for e in entries}, indent=2, sort_keys=True)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["kind", "key", "value"])
    for e in sorted(entries, key=lambda e: (e.key_kind, e.key)):
        writer.writerow([e.key_kind, e.key, e.value])
    return out.getvalue()


def diff(current: list[OverrideEntry], proposed: list[OverrideEntry]) -> dict[str, list]:
    """What importing `proposed` over `current` would add, change and leave (a diff never removes)."""
    have = {(e.key_kind, e.key): e for e in current}
    added, changed, same = [], [], []
    for e in proposed:
        existing = have.get((e.key_kind, e.key))
        (added if existing is None else same if existing.value == e.value else changed).append(e)
    return {"added": added, "changed": [(have[(e.key_kind, e.key)], e) for e in changed], "unchanged": same,
            "untouched": [e for k, e in have.items() if k not in {(p.key_kind, p.key) for p in proposed}]}


def scope(account: int | None, global_: bool) -> int:
    """The client id a command acts on: an account, or the global sentinel; exactly one must be named."""
    if (account is None) == (not global_):
        raise AdminError("name exactly one of --account <id> and --global")
    return GLOBAL_CLIENT if global_ else int(account)  # type: ignore[arg-type]
