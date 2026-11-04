"""A figure is never hedged: the structural rule behind "every figure is exact". [CH-15c]

Table-driven, because the rule is a pattern and the way to trust a pattern is to list what it
accepts and what it refuses. The rule is deliberately strict: it rejects, it does not read.
"""
from __future__ import annotations

import pytest

from application.composer import hedging as composer_hedging
from application.capabilities.envelope import DISCLAIMER, Block
from application.composer import compose, render_markdown
from application.numeric.guard import REJECTED

FACTS = {"credit": {"annual_credit_usd": 3500, "average_headcount": 12.67}, "client": {"reason": "On the line"}}
BLOCKS = [Block("table", rows=(("Measure", "Value"), ("Annual credit", "$3,500")))]
BLOCKS_ONLY = render_markdown(BLOCKS) + "\n\n" + DISCLAIMER
FIG = "{{facts.credit.annual_credit_usd|money}}"


def hedged(narration: str) -> int:
    from application.composer.substitution import _mask_placeholders

    return composer_hedging.hedged_figures(_mask_placeholders(narration))


@pytest.mark.parametrize("narration", [
    f"The credit is about {FIG}.",
    f"The credit is roughly {FIG}.",
    f"That comes to approximately {FIG}.",
    f"Around {FIG} is identified.",
    f"Nearly {FIG} is on the table.",
    f"The figure, rounded, is {FIG}.",
    f"Rounded, it is {FIG}.",
    f"It is {FIG} or so.",
    f"Up to {FIG} may be recoverable.",
    f"Close to {FIG} is identified.",
    f"It is {FIG}, give or take.",
    f"It is more or less {FIG}.",
    f"It is somewhere around {FIG}.",
    f"It is just over {FIG}.",
    f"Almost {FIG}.",
    f"~{FIG} is identified.",
    f"It is ~ {FIG}.",
    f"ABOUT {FIG}.",
    f"(about {FIG})",
    f"The credit is about, well, {FIG}.",
    f"The credit is not rounded, it is {FIG}.",
    f"This is not an approximation but it is roughly {FIG}.",
    f"The average headcount is about {{{{facts.credit.average_headcount}}}} people.",
    "The credit is roughly $3,500.",
])
def test_a_qualifier_next_to_a_figure_is_hedging(narration):
    assert hedged(narration) >= 1


@pytest.mark.parametrize("narration", [
    f"The credit is {FIG}.",
    f"The annual credit is {FIG} and the table shows the working.",
    "They are on the line, so call them first.",
    "Roughly speaking this client is the one to call, and the table shows why.",
    "About the credit: the table shows it.",
    f"They were about to cross the line; the credit is {FIG}.",
    f"Is this about them? The credit is {FIG}.",
    f"Both methods are shown below. The credit is {FIG}.",
    f"{FIG} is the credit, and you will find that around the third row of the table.",
    "",
])
def test_wording_that_does_not_hedge_a_figure_is_untouched(narration):
    assert hedged(narration) == 0


def test_the_window_is_three_tokens():
    assert hedged("about one two " + FIG) == 1
    assert hedged("about one two three " + FIG) == 0
    assert hedged(FIG + " one two about") == 1
    assert hedged(FIG + " one two three about") == 0


def test_each_hedged_figure_counts():
    assert hedged(f"About {FIG} and roughly {{{{facts.credit.average_headcount}}}}.") == 2


def test_a_hedge_that_is_split_by_punctuation_or_case_is_still_found():
    assert hedged(f"It is \u201cApproximately\u201d: {FIG}.") == 1
    assert hedged(f"It is UP TO {FIG}.") == 1


@pytest.mark.parametrize("narration", [
    f"The credit is about {FIG}.",
    f"The credit is not rounded: {FIG}.",
    f"Up to {FIG} may be recoverable.",
])
def test_compose_drops_a_hedged_narration_whole_and_shows_the_engines_answer(narration):
    reply = compose(BLOCKS, narration, FACTS)
    assert reply.narration_used is False
    assert reply.guard.status == REJECTED
    assert reply.text == BLOCKS_ONLY
    assert any(v.numeral.kind == "approximation" for v in reply.guard.violations)


def test_the_recorded_violation_never_repeats_the_words():
    reply = compose(BLOCKS, f"Roughly {FIG}, give or take.", FACTS)
    flat = repr(reply.to_dict())
    assert "Roughly" not in flat and "roughly" not in flat.replace("narration style", "")


def test_compose_keeps_a_plain_narration():
    reply = compose(BLOCKS, f"Their annual credit is {FIG}; the table shows the working.", FACTS)
    assert reply.narration_used is True and reply.guard.passed
    assert reply.text.startswith("Their annual credit is $3,500")


@pytest.mark.parametrize("narration", [
    "Rounded to the nearest thousand, you can see these figures in the table.",
    "I can't round these; the table shows them exactly.",
    "The figures are approximately where you would expect, see the table.",
    "Rounding is not applied, the table is exact.",
])
def test_saying_a_figure_was_rounded_is_rejected_even_with_no_figure_beside_it(narration):
    reply = compose(BLOCKS, narration, FACTS)
    assert reply.narration_used is False and reply.guard.status == REJECTED
    assert reply.text == BLOCKS_ONLY
    assert any(v.numeral.kind == "approximation" for v in reply.guard.violations)


def test_the_rounding_family_is_a_small_closed_set():
    assert composer_hedging.states_rounding("The table shows them exactly, around the page.") == 0
    assert composer_hedging.states_rounding("Round, rounded and approximately.") == 3


def test_a_hedge_beside_prose_only_is_fine_and_a_hedge_beside_a_figure_is_not():
    assert compose(BLOCKS, "Roughly speaking, call them first.", FACTS).narration_used is True
    assert compose(BLOCKS, f"Roughly {FIG}.", FACTS).narration_used is False
