"""A capability's `ToolResult` as the Ask workspace's evidence item. [CH-15d]

The contract is `docs/design/ASK-EVIDENCE-CONTRACT.md`. This module only RESHAPES
what the platform already rendered: a block's text and rows pass through
character for character, so the right-hand pane can never show a figure the
engine did not write. Nothing here formats, rounds, sorts or computes, and no
model text can reach it.

Who may see employee rows is decided here, once. A sensitive capability's table
is withheld from a caller who is not signed in and replaced by a sentence that
keeps the count, because "12 rows withheld" is honest and an empty table reads
as "nobody".
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from application.capabilities.catalog import BY_NAME
from application.capabilities.envelope import Block, ToolResult

#: The tab label for each chat intent. A label says WHICH question the tab answers;
#: the tool's own name ("client_discovery") is shared by two intents.
INTENT_TITLE: dict[str, str] = {
    "book": "Who to call",
    "situation": "Situation",
    "eligibility": "Eligibility",
    "at_risk": "At risk",
    "trend": "Trend",
    "multi_state": "All programmes",
    "discovery": "Other programmes",
    "simulate": "What-if",
    "explain": "Calculation",
}

_PROVENANCE_KEYS = {"run_id": "run_id", "rule_pack_version": "rule_pack", "trail_sha256": "trail_hash"}


def _scalar_facts(facts: Mapping[str, Any]) -> dict[str, str]:
    """Top-level scalar facts as the exact strings the engine holds. Nested values are left out."""
    out: dict[str, str] = {}
    for key, value in facts.items():
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, Decimal):
            out[str(key)] = format(value, "f")
        elif isinstance(value, (str, int, float)):
            out[str(key)] = str(value)
    return out


def _table(block: Block, title: str | None, *, show_rows: bool) -> dict[str, Any]:
    """The first row is the header, as the envelope lays it out."""
    header, body = (list(block.rows[0]), [list(r) for r in block.rows[1:]]) if block.rows else ([], [])
    if show_rows:
        return {"kind": "table", "title": title, "columns": header, "rows": body}
    noun = "row" if len(body) == 1 else "rows"
    label = f"{title}: " if title else ""
    return {
        "kind": "text", "title": None,
        "text": f"{label}{len(body)} {noun} withheld. Employee-level rows are shown to a signed-in user only.",
    }


def _blocks(blocks: Iterable[Block], *, show_rows: bool) -> list[dict[str, Any]]:
    """Envelope blocks as contract blocks. A heading titles the block after it."""
    out: list[dict[str, Any]] = []
    heading: str | None = None
    for block in blocks:
        if block.kind == "heading":
            if heading is not None:
                out.append({"kind": "text", "title": None, "text": heading})
            heading = block.text
            continue
        title, heading = heading, None
        if block.kind == "table":
            out.append(_table(block, title, show_rows=show_rows))
        elif block.kind == "bullets":
            out.append({"kind": "list", "title": title, "rows": [row[0] for row in block.rows]})
        elif block.kind == "callout":
            out.append({"kind": "callout", "title": title, "text": block.text})
        else:
            out.append({"kind": "text", "title": title, "text": block.text})
    if heading is not None:
        out.append({"kind": "text", "title": None, "text": heading})
    return out


def _provenance(result: ToolResult) -> dict[str, str]:
    """The fields the contract names; a field the envelope does not hold is absent, never invented."""
    held = result.provenance.to_dict()
    return {wire: str(held[field]) for field, wire in _PROVENANCE_KEYS.items() if held.get(field)}


def _drop_nulls(item: dict[str, Any]) -> dict[str, Any]:
    for block in item["blocks"]:
        if block.get("title") is None:
            block.pop("title", None)
    return item


def evidence_item(intent: str, result: ToolResult, ordinal: int, *, authenticated: bool) -> dict[str, Any] | None:
    """The evidence item for one capability that ran, or None when it rendered nothing.

    `tool` is the chat INTENT, the name the `plan` event carried, so the pane can
    match a tab to the capability it planned. An unknown tool is treated as
    sensitive: withholding rows from something unclassified is the safe error.
    """
    spec = BY_NAME.get(result.tool)
    withhold = spec is None or (spec.sensitive and not authenticated)
    blocks = _blocks(result.blocks, show_rows=not withhold)
    blocks += [{"kind": "callout", "title": "Note", "text": w, "tone": "partial"} for w in result.warnings]
    if not blocks:
        return None
    item: dict[str, Any] = {
        "id": f"ev-{intent}-{ordinal}",
        "tool": intent,
        "kind": "evidence",
        "title": INTENT_TITLE.get(intent, intent),
        "facts": {} if withhold else _scalar_facts(result.facts),
        "blocks": blocks,
        "disclaimer": result.disclaimer,
    }
    provenance = _provenance(result)
    if provenance:
        item["provenance"] = provenance
    return _drop_nulls(item)
