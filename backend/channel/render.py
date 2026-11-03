"""The text a Cowork model reads, rendered by the platform. [CH-06, ADR-008]

Cowork composes its own answers, so what it quotes is whatever text we hand it. That
text is built here, from the envelope's `blocks`, by the same renderer the composer
uses — deterministic, no model — preceded by an instruction to quote verbatim and
followed by the standing disclaimer. A figure appears in it only because a block
carried it.

Two lines are added where a caller needs a value that is not a figure: a write
preview's confirmation token (the model must pass it to the commit tool) and a
claim package's download address (absolute, built from the address the caller used).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.capabilities.envelope import DISCLAIMER, Block
from application.composer_render import render_markdown

VERBATIM = "VERBATIM — quote figures exactly as written."


def blocks_from(envelope: Mapping[str, Any]) -> list[Block]:
    """The envelope's blocks, as `Block`s again, so the one renderer serves every caller."""
    return [
        Block(b["kind"], text=b.get("text", ""), rows=tuple(tuple(r) for r in b.get("rows", [])))
        for b in envelope.get("blocks", [])
    ]


def _handover_lines(facts: Mapping[str, Any], base_url: str) -> list[str]:
    lines: list[str] = []
    confirmation = facts.get("confirmation")
    if isinstance(confirmation, Mapping) and confirmation.get("token"):
        lines.append(
            f"Confirmation token (pass it to the matching commit tool only after the user confirms): {confirmation['token']}"
        )
    path = facts.get("download_path")
    if isinstance(path, str) and path.startswith("/channel/"):
        lines.append(f"Download (single use, for this user only): {base_url.rstrip('/')}{path}")
    return lines


def render_tool_text(envelope: Mapping[str, Any], base_url: str = "") -> str:
    """The complete text block for one tool result."""
    body = render_markdown(blocks_from(envelope))
    parts = [VERBATIM, body, *_handover_lines(envelope.get("facts") or {}, base_url),
             envelope.get("disclaimer") or DISCLAIMER]
    return "\n\n".join(p for p in parts if p)


def render_error_text(error: Mapping[str, Any]) -> str:
    """A refusal, said plainly. The code is stable; the message is safe to show."""
    return f"The request did not go through ({error.get('code')}): {error.get('message')}"
