"""No hedging next to a figure: the structural half of "every figure is exact". [CH-15c]

The numeric guard proves a numeral IS the engine's figure; it cannot see that a sentence
then describes it as less than that. Live, a narrator called an exact credit "rounded",
and "roughly {{facts.x}}" would pass every digit check while telling a tax consultant the
figure is soft. This module closes that gap by structure, not by meaning: if an
approximation qualifier ("about", "roughly", "nearly", "up to", "rounded"...) sits within
three tokens of a figure, the narration is rejected.

It never tries to understand the sentence. "Not rounded" and "rounded" are rejected alike,
because a rule that parsed negation would be a second, weaker language model sitting where
a pattern should be, and a rejected narration costs the reader nothing: they see the
engine's own answer without the commentary.

The check runs on the narrator's words with every placeholder standing as one opaque
figure token (`composer_placeholders._mask_placeholders`), so a placeholder is a figure by
construction and the check needs no knowledge of how the formatter prints it. A token that
contains a digit (a numeral the guard will reject anyway) counts as a figure too.

Standard library only: vendored beside the composer into the orchestrator container.
"""
from __future__ import annotations

import re

#: Tokens that hedge a figure. Single words, compared lower-case without punctuation.
QUALIFIER_WORDS = frozenset({
    "about", "around", "roughly", "approximately", "approx", "approximate", "approximated", "nearly",
    "almost", "circa", "rounded", "rounding",     "round", "ballpark",
    })
#: Multi-word hedges, as token tuples.
QUALIFIER_PHRASES = (
    ("up", "to"), ("close", "to"), ("or", "so"), ("more", "or", "less"), ("give", "or", "take"),
    ("in", "the", "region", "of"), ("on", "the", "order", "of"), ("just", "over"), ("just", "under"),
    ("just", "above"), ("just", "below"), ("a", "little", "over"), ("a", "little", "under"),
    ("somewhere", "around"), ("in", "the", "ballpark"),
)
#: How many tokens may separate a qualifier from a figure, counting the figure's own position.
WINDOW = 3

_TOKEN = re.compile(r"\S+")
_EDGE = re.compile(r"^[^\w~\u2588]+|[^\w~\u2588]+$")
_HOLE = "\u2588"


def _tokens(text: str) -> list[str]:
    """Whitespace tokens, lower-cased and stripped of surrounding punctuation."""
    return [_EDGE.sub("", raw.lower()) for raw in _TOKEN.findall(text)]


def _is_figure(token: str) -> bool:
    return _HOLE in token or any(ch.isdigit() for ch in token)


def _qualifier_positions(tokens: list[str]) -> set[int]:
    """Every token index that belongs to a hedge, single word or phrase."""
    found = {i for i, token in enumerate(tokens) if token in QUALIFIER_WORDS or token.startswith("~")}
    for phrase in QUALIFIER_PHRASES:
        size = len(phrase)
        for start in range(len(tokens) - size + 1):
            if tuple(tokens[start:start + size]) == phrase:
                found.update(range(start, start + size))
    return found


#: Words that say a figure was rounded or approximated. The narrator may never use them at all
#: ("never say a figure is rounded, even to deny it"): live, "Rounded to the nearest thousand, you can see
#: these figures in the table" passed the window rule because no figure sat beside the word, and it told the
#: reader a rounding had happened when the engine's exact figures were shown.
ROUNDING_WORDS = frozenset({"rounded", "rounding", "round", "approximate", "approximately", "approximated", "approx"})


def states_rounding(masked: str) -> int:
    """How many tokens of `masked` say something was rounded or approximated, wherever they sit."""
    return sum(1 for token in _tokens(masked) if token in ROUNDING_WORDS)


def hedged_figures(masked: str) -> int:
    """How many figures in `masked` sit within three tokens of an approximation qualifier.

    `masked` is the narration with each placeholder replaced by one opaque token
    (`\u2588`). Zero means the wording does not hedge any figure.
    """
    tokens = _tokens(masked)
    hedges = _qualifier_positions(tokens)
    if not hedges:
        return 0
    return sum(
        1 for i, token in enumerate(tokens)
        if _is_figure(token) and any(abs(i - h) <= WINDOW for h in hedges)
    )
