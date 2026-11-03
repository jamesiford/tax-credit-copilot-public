"""The platform's blocks, rendered. [ADR-008]

Markdown for the channel, and a neutral structure the orchestrator turns into
Adaptive Cards. Pure formatting: no figure is added, changed or computed here, which
is why a reply's blocks can always be trusted when its narration cannot. Split out of
`composer`, which re-exports both functions.

Standard library only, plus the envelope: vendored.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from application.capabilities.envelope import DISCLAIMER, Block


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(blocks: Sequence[Block]) -> str:
    """The platform's blocks as Markdown. Pure formatting: no figure is added."""
    parts: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            parts.append(f"### {block.text}")
        elif block.kind in ("paragraph",):
            parts.append(block.text)
        elif block.kind == "callout":
            parts.append("\n".join(f"> {line}" for line in block.text.splitlines() or [""]))
        elif block.kind == "bullets":
            parts.append("\n".join(f"- {row[0]}" for row in block.rows))
        elif block.kind == "table" and block.rows:
            header, *body = block.rows
            lines = [
                "| " + " | ".join(_escape_cell(c) for c in header) + " |",
                "| " + " | ".join("---" for _ in header) + " |",
                *("| " + " | ".join(_escape_cell(c) for c in row) + " |" for row in body),
            ]
            parts.append("\n".join(lines))
    return "\n\n".join(p for p in parts if p)


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
        elif block.kind == "heading":
            body.append({"type": "heading", "text": block.text})
        elif block.kind == "paragraph":
            body.append({"type": "paragraph", "text": block.text})
        elif block.kind == "callout":
            body.append({"type": "callout", "text": block.text})
        elif block.kind == "bullets":
            body.append({"type": "bullets", "items": [row[0] for row in block.rows]})
        elif block.kind == "table" and block.rows:
            header, *rows = block.rows
            if len(header) == 2:
                body.append({"type": "facts", "columns": list(header), "rows": [list(r) for r in rows]})
            else:
                body.append({"type": "table", "columns": list(header), "rows": [list(r) for r in rows]})
    return {"title": title, "body": body, "disclaimer": disclaimer}
