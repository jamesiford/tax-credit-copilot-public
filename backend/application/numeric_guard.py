"""The numeric integrity guard [ADR-008].

A figure on a tax return is either the engine's figure or it is wrong, and a
language model can misstate a number it was handed as easily as it can invent
one. So nothing a model writes reaches a reader unless every numeral in it can be
traced to a value the engine produced. This module is that check.

**Zero tolerance.** A numeral passes only if it *equals* a fact (exact `Decimal`
equality — no rounding allowance, no "close enough"), or it appeared in the
reader's own question or the resolved scope, or it is structural (a list marker,
a step number, a small ordinal). An abbreviation (`$3.5K`, `1.2 million`) passes
only if the formatter would have printed exactly that spelling. A rejected
sentence is an inconvenience; a wrong figure on a tax return is not.

**What counts as a numeral.** Plain and grouped numbers, decimals (with or
without a leading digit), negatives (`-3`, `(3)`), money, percentages,
abbreviations, ranges (each end is its own numeral), numbers next to units
(`12.67 FTE`), ISO dates and `TY2023`-style tokens. Number *words* ("twelve") are
not numerals here — the narrator's prompt forbids them for figures, and a guard
that guessed at English would be wrong in both directions. Digits that are not
ASCII (full-width, Arabic-Indic, vulgar fractions) are rejected outright rather
than normalised: no formatter emits them, so their only use is evasion.

**Where the pieces live.** The rule is here; the parts it uses were split out by
size and are re-exported below, so every import path is unchanged:
`numeric_types` (Numeral, Violation, GuardResult), `numeric_extract` (finding the
numerals), `numeric_context` (what the reader supplied) and `numeric_facts` (what
the engine said).

**Standard library only**, plus `application.capabilities.format` and the sibling
`numeric_*` modules, which are themselves standard-library only. All are vendored
into the orchestrator container.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from application.numeric_context import AllowedContext
from application.numeric_extract import (  # noqa: F401 - re-exported
    MAX_LIST_MARKER, MAX_ORDINAL, MAX_STEP, extract_numerals,
)
from application.numeric_facts import FactIndex, _flatten  # noqa: F401 - re-exported
from application.numeric_types import PASS, REJECTED, GuardResult, Numeral, Violation


def _judge(numeral: Numeral, facts: FactIndex, context: AllowedContext) -> str | None:
    """Why this numeral is not acceptable, or None if it is."""
    kind, value = numeral.kind, numeral.value
    if kind == "structural":
        return None
    if kind == "non_ascii":
        return "a digit or numeric character that no formatter emits (non-ASCII, or split by a space)"
    if kind == "date":
        if numeral.text in facts.dates or numeral.text in context.surfaces:
            return None
        return "a date that is not in the facts"
    if value is None:
        return "a numeral with no value"
    if kind == "ordinal" and 1 <= value <= MAX_ORDINAL:
        return None
    if numeral.abbreviated:
        if numeral.text in facts.spellings or numeral.text in context.surfaces:
            return None
        return "an abbreviation the formatter did not emit"
    if numeral.percent:
        if value in facts.percent_values or value in context.percents:
            return None
        return "a percentage that is not in the facts"
    if value in facts.values or value in context.values:
        return None
    if kind == "year" and int(value) in context.years:
        return None
    return "a figure that is not in the facts"


def check(
    text: str,
    *,
    facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]",
    allowed_context: AllowedContext | None = None,
    stage: str = "final",
) -> GuardResult:
    """Every numeral in `text` must be a fact, supplied context, or structural.

    Returns `rejected` with each offending numeral and the nearest fact value
    (what a changed digit was probably meant to be). It never softens, rounds or
    rewrites: the caller decides what to show instead.
    """
    index = FactIndex.coerce(facts)
    context = allowed_context or AllowedContext()
    violations = []
    for numeral in extract_numerals(text):
        reason = _judge(numeral, index, context)
        if reason is not None:
            nearest = index.nearest(numeral.value) if numeral.value is not None else None
            violations.append(Violation(numeral, reason, stage=stage, nearest=nearest))
    return GuardResult(REJECTED if violations else PASS, tuple(violations))


def check_raw(text: str, *, allowed_context: AllowedContext | None = None) -> GuardResult:
    """The strict gate on a model's own words: no digit unless the reader supplied it.

    Run before placeholders are substituted. A figure belongs in a placeholder; a
    numeral a model typed — even one that happens to equal a fact — is the model
    producing a number, which is exactly what the architecture forbids. Only the
    reader's own numerals and structural digits pass.
    """
    return check(text, facts=FactIndex(), allowed_context=allowed_context, stage="narration")
