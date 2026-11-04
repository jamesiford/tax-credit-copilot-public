"""The platform's blocks, rendered. [ADR-008]

Markdown for the channel, and a neutral structure the orchestrator turns into
Adaptive Cards. Pure formatting: no figure is added, changed or computed here, which
is why a reply's blocks can always be trusted when its narration cannot. The package
`application.composer` re-exports both functions.

Standard library only, plus the envelope: vendored.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from application.capabilities.envelope import DISCLAIMER, Block


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _quote(block: Block) -> str:
    return "\n".join(f"> {line}" for line in block.text.splitlines() or [""])


def _markdown_table(block: Block) -> str:
    if not block.rows:
        return ""
    header, *body = block.rows
    lines = [
        "| " + " | ".join(_escape_cell(c) for c in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(_escape_cell(c) for c in row) + " |" for row in body),
    ]
    return "\n".join(lines)


#: Block kind -> its Markdown. A kind not listed renders nothing, as it always has.
_MARKDOWN: dict[str, Callable[[Block], str]] = {
    "heading": lambda block: f"### {block.text}",
    "paragraph": lambda block: block.text,
    "callout": _quote,
    "bullets": lambda block: "\n".join(f"- {row[0]}" for row in block.rows),
    "table": _markdown_table,
}


def render_markdown(blocks: Sequence[Block]) -> str:
    """The platform's blocks as Markdown. Pure formatting: no figure is added."""
    parts = (_MARKDOWN[block.kind](block) for block in blocks if block.kind in _MARKDOWN)
    return "\n\n".join(p for p in parts if p)


def _card_table(block: Block) -> dict[str, Any] | None:
    if not block.rows:
        return None
    header, *rows = block.rows
    kind = "facts" if len(header) == 2 else "table"
    return {"type": kind, "columns": list(header), "rows": [list(r) for r in rows]}


#: Block kind -> its card item, or None for nothing. The title is the one stateful rule and stays in the loop.
_CARD_ITEM: dict[str, Callable[[Block], dict[str, Any] | None]] = {
    "heading": lambda block: {"type": "heading", "text": block.text},
    "paragraph": lambda block: {"type": "paragraph", "text": block.text},
    "callout": lambda block: {"type": "callout", "text": block.text},
    "bullets": lambda block: {"type": "bullets", "items": [row[0] for row in block.rows]},
    "table": _card_table,
}


def cards_payload(blocks: Sequence[Block], *, disclaimer: str = DISCLAIMER) -> dict[str, Any]:
    """A neutral structure for the orchestrator to turn into Adaptive Cards.

    The first heading is the title. A two-column table is a list of facts; any
    other table keeps its columns. No Adaptive Card JSON here — that is a
    presentation concern and belongs to the channel.
    """
    title: str | None = None
    body: list[dict[str, Any]] = []
    for block in blocks:
        if block.kind == "heading" and title is None and not body:
            title = block.text
            continue
        item = _CARD_ITEM.get(block.kind, lambda _: None)(block)
        if item is not None:
            body.append(item)
    return {"title": title, "body": body, "disclaimer": disclaimer}