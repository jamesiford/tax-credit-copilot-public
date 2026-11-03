"""Placeholders: how a narrator names a figure without writing it. [ADR-008]

A narrator writes `{{facts.credit.annual_credit_usd}}`; this module substitutes the
engine's figure through the one formatter. It also builds the brief the narrator is
handed — the NAMES of the facts, never their values — because a model that has not
seen a figure cannot copy it as a digit. Split out of `composer`, which re-exports
everything here.

Standard library only, plus the formatter and the guard's fact index: vendored.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from application.capabilities import format as fmt
from application.numeric_guard import FactIndex

_PLACEHOLDER = re.compile(r"\{\{\s*facts\.([^{}|\s]+?)\s*(?:\|\s*([A-Za-z_]+)\s*)?\}\}")
_ANY_BRACES = re.compile(r"\{\{|\}\}")
_FENCE = re.compile(r"^[ \t]*(```|~~~)", re.MULTILINE)

#: Stands where a placeholder was while the raw narration is checked. A letter,
#: so it can never join with a neighbouring digit into a numeral.
_HOLE = "\u2588"


class PlaceholderError(ValueError):
    """A placeholder that cannot be rendered exactly. Never rendered as a guess."""


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
    """Every placeholder in `text`, in order."""
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
