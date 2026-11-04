"""The text a Cowork model reads, rendered by the platform. [CH-06, ADR-008]

Cowork composes its own answers, so what it quotes is whatever text we hand it. That
text is built here, from the envelope's `blocks`, by the same renderer the composer
uses — deterministic, no model — preceded by an instruction to quote verbatim and
followed by the standing disclaimer. A figure appears in it only because a block
carried it.

Two lines are added where a caller needs a value that is not a figure: a write
preview's confirmation token (the model must pass it to the commit tool) and a
claim package's download address (absolute, built from the address the caller used).
A third, the provenance line (run, rule pack, assumption set, trail hash), lets a
document footer be copied rather than invented. [CH-10]
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.capabilities.envelope import AUDIENCE_USER, AUDIENCES, DISCLAIMER, Block
from application.composer_render import render_markdown

VERBATIM = "VERBATIM — quote figures exactly as written."


def blocks_from(envelope: Mapping[str, Any]) -> list[Block]:
    """The envelope's blocks, as `Block`s again, so the one renderer serves every caller.

    An audience this build does not know is read as the person-only lane, never as `both`.
    """
    out = []
    for b in envelope.get("blocks", []):
        said = b.get("audience", "both")
        out.append(Block(b["kind"], text=b.get("text", ""), rows=tuple(tuple(r) for r in b.get("rows", [])),
                         audience=said if said in AUDIENCES else AUDIENCE_USER))
    return out


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


_PROVENANCE_LABELS = (
    ("run_id", "run"), ("rule_pack_version", "rule pack"), ("assumption_set_id", "assumptions"), ("trail_sha256", "trail hash"),
)


def provenance_line(envelope: Mapping[str, Any]) -> str:
    """One line naming the run, rule pack, assumption set and trail hash behind a result, or "" when it has none.

    A skill that builds a footer for a briefing needs these values as text. They also
    arrive in `structuredContent`, but a client that shows the model only the text block
    would otherwise have nothing to copy, and a model that cannot copy an identifier
    will write one. The label says "trail hash", not "sha256": the figure check reads
    the digits of a digest as numerals, and the word would add one more.
    """
    provenance = envelope.get("provenance") or {}
    parts = [f"{label} {provenance[key]}" for key, label in _PROVENANCE_LABELS if provenance.get(key)]
    return "Provenance: " + "; ".join(parts) + "." if parts else ""


def render_tool_text(envelope: Mapping[str, Any], base_url: str = "") -> str:
    """The complete text block for one tool result."""
    body = render_markdown(blocks_from(envelope))
    parts = [VERBATIM, body, *_handover_lines(envelope.get("facts") or {}, base_url), provenance_line(envelope),
             envelope.get("disclaimer") or DISCLAIMER]
    return "\n\n".join(p for p in parts if p)


def render_error_text(error: Mapping[str, Any]) -> str:
    """A refusal, said plainly. The code is stable; the message is safe to show."""
    return f"The request did not go through ({error.get('code')}): {error.get('message')}"
