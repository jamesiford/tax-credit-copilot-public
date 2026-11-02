"""The response composer [ADR-008].

A reply is assembled **in code**, from the platform's `blocks`, with a narrator's
prose around them. The narrator may write the connective sentences; it may not
write a figure. A figure appears in a reply only as a placeholder —
`{{facts.credit.annual_credit_usd}}`, optionally `{{facts.x|money}}` — that this
module substitutes through the one formatter, and every reply is checked twice:

1. **Before substitution**, the narrator's raw words go through
   `numeric_guard.check_raw`. Any digit outside a placeholder that the reader did
   not supply themselves rejects the narration: the model typed a number.
2. **After substitution**, the whole reply goes through `numeric_guard.check`
   against the fact index. That is defence in depth against a formatter bug — the
   first gate trusts the formatter, the second does not.

If either fails, the reply is the platform's own blocks and the standing
disclaimer, nothing else. The composer never softens, rounds or patches a
sentence: a rejected narration is dropped whole and the reader sees the engine's
words instead, with the violations returned so the caller can audit them.

Standard library only, plus the guard, the formatter and the envelope — all
standard-library only themselves, and all vendored into the orchestrator
container.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from application import numeric_guard
from application.capabilities import format as fmt
from application.capabilities.envelope import DISCLAIMER, Block
from application.numeric_guard import AllowedContext, FactIndex, GuardResult, Numeral, Violation

_PLACEHOLDER = re.compile(r"\{\{\s*facts\.([^{}|\s]+?)\s*(?:\|\s*([A-Za-z_]+)\s*)?\}\}")
_ANY_BRACES = re.compile(r"\{\{|\}\}")
_FENCE = re.compile(r"^[ \t]*(```|~~~)", re.MULTILINE)

#: Stands where a placeholder was while the raw narration is checked. A letter,
#: so it can never join with a neighbouring digit into a numeral.
_HOLE = "\u2588"


class PlaceholderError(ValueError):
    """A placeholder that cannot be rendered exactly. Never rendered as a guess."""


@dataclass(frozen=True)
class Composed:
    """A finished reply.

    `text` is Markdown for the channel; `cards_payload` is a neutral structure the
    orchestrator turns into Adaptive Cards (no card JSON lives here). `guard` is the
    verdict that decided what `text` contains, and `narration_used` says whether
    the narrator's prose survived it.
    """

    text: str
    cards_payload: dict[str, Any]
    guard: GuardResult
    narration_used: bool
    blocks_verified: bool = True
    notice: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "cards": self.cards_payload, "guard": self.guard.to_dict(),
            "narration_used": self.narration_used, "blocks_verified": self.blocks_verified,
            "notice": self.notice,
        }


# --------------------------------------------------------------- placeholders


def _fenced_ranges(text: str) -> list[tuple[int, int]]:
    """Character ranges that sit inside a fenced code block."""
    ranges: list[tuple[int, int]] = []
    opener: re.Match[str] | None = None
    for match in _FENCE.finditer(text):
        if opener is None:
            opener = match
        elif match.group(1) == opener.group(1):
            ranges.append((opener.start(), match.end()))
            opener = None
    if opener is not None:
        ranges.append((opener.start(), len(text)))
    return ranges


def placeholders(text: str) -> list[re.Match[str]]:
    return list(_PLACEHOLDER.finditer(text))


def substitute(narration: str, facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]") -> tuple[str, FactIndex]:
    """Replace every `{{facts.path|format}}` with the engine's figure, formatted.

    Returns the text and the fact index, told which paths were rendered as
    percentages so the final guard accepts exactly those spellings. Raises
    `PlaceholderError` for anything it cannot render exactly: an unknown or
    ambiguous path, a path that is not a single value, a null, an unknown
    formatter, a value the formatter refuses, a placeholder inside a code fence,
    or braces that are not a well-formed placeholder.
    """
    index = FactIndex.coerce(facts)
    fences = _fenced_ranges(narration)
    rendered: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER.finditer(narration):
        if any(start <= match.start() < end for start, end in fences):
            raise PlaceholderError(
                f"placeholder {match.group(0)!r} is inside a code fence, where its formatting cannot be trusted"
            )
        path, name = match.group(1), match.group(2)
        if path in index.ambiguous:
            raise PlaceholderError(f"facts.{path} is defined differently by more than one result")
        if path not in index.leaves:
            raise PlaceholderError(f"unknown fact path facts.{path}")
        value = index.leaves[path]
        if value is None:
            raise PlaceholderError(f"facts.{path} is null; there is no figure to render")
        formatter = name or fmt.infer_formatter(path, value)
        if formatter not in fmt.FORMATTERS:
            raise PlaceholderError(f"unknown formatter {formatter!r} for facts.{path}")
        try:
            text = fmt.format_value(value, formatter)
        except ValueError as exc:
            raise PlaceholderError(f"facts.{path} cannot be rendered as {formatter}: {exc}") from exc
        if formatter in fmt.PERCENT_FORMATTERS:
            index = index.with_percent(path)
        rendered.append(narration[cursor:match.start()])
        rendered.append(text)
        cursor = match.end()
    rendered.append(narration[cursor:])
    out = "".join(rendered)
    stray = _ANY_BRACES.search(_PLACEHOLDER.sub("", narration))
    if stray:
        raise PlaceholderError("braces that are not a well-formed {{facts.path}} placeholder")
    return out, index


def _mask_placeholders(narration: str) -> str:
    return _PLACEHOLDER.sub(_HOLE, narration)


def narrator_brief(
    question: str,
    tools: Sequence[str],
    facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]",
    *,
    notes: Sequence[str] = (),
    declined: str | None = None,
) -> dict[str, Any]:
    """What the narrator is handed: the NAMES of the facts, never their values.

    A model that has not seen a figure cannot copy it as a digit. It is told
    which paths exist and how each prints, writes a placeholder, and the engine's
    own rendering is substituted afterwards. `notes` are platform sentences it
    may paraphrase; `declined` is a statute refusal to restate plainly.
    """
    index = FactIndex.coerce(facts)
    return {
        "question": question,
        "tools": list(tools),
        "fact_paths": [
            {"path": path, "format": fmt.infer_formatter(path, value)}
            for path, value in sorted(index.leaves.items())
            if value is not None and not isinstance(value, bool)
        ],
        "notes": list(notes),
        "declined": declined,
    }


# ---------------------------------------------------------------------- blocks


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


# --------------------------------------------------------------------- compose


def _verdict(violations: Sequence[Violation]) -> GuardResult:
    return GuardResult(numeric_guard.REJECTED if violations else numeric_guard.PASS, tuple(violations))


def _placeholder_violation(message: str) -> Violation:
    return Violation(Numeral(message, 0, 0, "placeholder"), message, stage="narration")


def compose(
    blocks: Sequence[Block],
    narration: str | None,
    facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]",
    allowed_context: AllowedContext | None = None,
    *,
    disclaimer: str = DISCLAIMER,
) -> Composed:
    """Assemble one reply, or fall back to the platform's blocks alone.

    The narration, when it survives, sits above the blocks; the disclaimer is
    always last. The guard that decided the outcome is returned either way.
    """
    index = FactIndex.coerce(facts)
    context = allowed_context or AllowedContext()
    blocks_md = render_markdown(blocks)
    cards = cards_payload(blocks, disclaimer=disclaimer)

    narrated = ""
    violations: list[Violation] = []
    if narration and narration.strip():
        # 1. The model's own words, before any figure is substituted.
        violations.extend(numeric_guard.check_raw(_mask_placeholders(narration), allowed_context=context).violations)
        try:
            substituted, index = substitute(narration, index)
        except PlaceholderError as exc:
            violations.append(_placeholder_violation(str(exc)))
        else:
            narrated = substituted.strip()

    if not violations and narrated:
        # 2. The finished reply, against the facts, trusting no formatter.
        full = "\n\n".join(p for p in (narrated, blocks_md, disclaimer) if p)
        final = numeric_guard.check(full, facts=index, allowed_context=context)
        if final.passed:
            return Composed(full, cards, final, narration_used=True)
        violations.extend(final.violations)

    fallback = "\n\n".join(p for p in (blocks_md, disclaimer) if p)
    if not blocks_md:
        return Composed(fallback, cards, _verdict(violations), narration_used=False)

    # The blocks are platform-rendered, so they should always pass. If they do
    # not, a formatter is wrong, and the one thing worse than dropping the
    # narration is showing a figure nothing can vouch for.
    blocks_guard = numeric_guard.check(fallback, facts=index, allowed_context=context)
    if blocks_guard.passed:
        return Composed(fallback, cards, _verdict(violations), narration_used=False)
    notice = (
        "The figures in this answer could not be verified against the engine's output, "
        "so none are shown."
    )
    return Composed(
        "\n\n".join((notice, disclaimer)), {"title": None, "body": [], "disclaimer": disclaimer},
        _verdict([*violations, *blocks_guard.violations]),
        narration_used=False, blocks_verified=False, notice=notice,
    )
