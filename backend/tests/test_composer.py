"""The composer: figures only through placeholders, checked before and after.

The properties under test, in the order a reply is built:

* a placeholder renders the engine's figure through the one formatter, and
  refuses (never guesses) anything it cannot render exactly;
* a narrator that types a figure — even a correct one — loses its narration;
* a formatter that prints a wrong figure is caught by the second, final check;
* on any rejection the reply is the platform's blocks and the disclaimer, and
  nothing else;
* and the composer depends on the guard being consulted.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from application import composer, numeric_guard
from application.capabilities import format as fmt
from application.capabilities.envelope import DISCLAIMER, Block
from application.composer import PlaceholderError, compose, render_markdown, substitute
from application.numeric_guard import AllowedContext, FactIndex, GuardResult, PASS, REJECTED

FACTS = {
    "credit": {
        "citation": "O.C.G.A. 48-7-40.26",
        "annual_credit_usd": 3500,
        "average_headcount": 12.67,
        "qualifying_jobs": None,
    },
    "population": {"min_max_eligible": 539, "ratio": 0.125},
    "snapshot": {"selected_tax_year": 2023, "begin": "2023-07-28"},
}

BLOCKS = [
    Block("heading", text="Georgia Jobs Tax Credit"),
    Block("table", rows=(
        ("Measure", "Value"),
        ("Annual credit", fmt.money(3500)),
        ("Average headcount", fmt.headcount(12.67)),
        ("Eligible employees", fmt.count(539)),
    )),
    Block("paragraph", text="Citation: O.C.G.A. 48-7-40.26"),
]
BLOCKS_ONLY = render_markdown(BLOCKS) + "\n\n" + DISCLAIMER
CONTEXT = AllowedContext.build(years=[2023])


# ---------------------------------------------------------------- placeholders


@pytest.mark.parametrize("narration, expected", [
    ("{{facts.credit.annual_credit_usd}}", "$3,500"),
    ("{{facts.credit.annual_credit_usd|money}}", "$3,500"),
    ("{{ facts.credit.annual_credit_usd | money }}", "$3,500"),
    ("{{facts.credit.annual_credit_usd|compact_money}}", "$3.5K"),
    ("{{facts.credit.annual_credit_usd|number}}", "3,500"),
    ("{{facts.credit.average_headcount}}", "12.67"),
    ("{{facts.population.min_max_eligible}}", "539"),
    ("{{facts.population.min_max_eligible|count}}", "539"),
    ("{{facts.population.ratio|percent}}", "12.5%"),
    ("{{facts.snapshot.selected_tax_year}}", "2023"),
    ("{{facts.snapshot.begin}}", "2023-07-28"),
    ("{{facts.credit.citation}}", "O.C.G.A. 48-7-40.26"),
    ("up {{facts.credit.annual_credit_usd}} from {{facts.population.min_max_eligible}} people",
     "up $3,500 from 539 people"),
])
def test_a_placeholder_renders_through_the_formatter(narration, expected):
    text, _index = substitute(narration, FACTS)
    assert text == expected


def test_percent_rendering_tells_the_index_the_fact_is_a_percentage():
    _text, index = substitute("{{facts.population.ratio|percent}}", FACTS)
    assert numeric_guard.check("12.5%", facts=index).passed
    assert not numeric_guard.check("12.5%", facts=FactIndex.from_facts(FACTS)).passed


@pytest.mark.parametrize("narration, message", [
    ("{{facts.credit.nope}}", "unknown fact path"),
    ("{{facts.credit}}", "unknown fact path"),
    ("{{facts.credit.annual_credit_usd|accounting}}", "unknown formatter"),
    ("{{facts.credit.annual_credit_usd|Money}}", "unknown formatter"),
    ("{{facts.credit.qualifying_jobs}}", "is null"),
    ("{{facts.credit.citation|money}}", "cannot be rendered as money"),
    ("{{facts.credit.average_headcount|count}}", "cannot be rendered as count"),
    ("{{facts.credit.annual_credit_usd|year}}", "cannot be rendered as year"),
    ("{{facts.}}", "not a well-formed"),
    ("{{credit.annual_credit_usd}}", "not a well-formed"),
    ("{{facts.credit.annual_credit_usd}", "not a well-formed"),
    ("```\n{{facts.credit.annual_credit_usd}}\n```", "code fence"),
    ("text\n~~~\n{{facts.credit.annual_credit_usd}}\n~~~", "code fence"),
])
def test_a_placeholder_that_cannot_be_rendered_exactly_raises(narration, message):
    with pytest.raises(PlaceholderError, match=message):
        substitute(narration, FACTS)


def test_a_placeholder_after_a_closed_fence_is_fine():
    text, _ = substitute("```\ncode\n```\nthen {{facts.population.min_max_eligible}}", FACTS)
    assert text.endswith("then 539")


def test_a_path_two_results_define_differently_cannot_be_used():
    index = FactIndex.from_facts([{"a": {"x": 1}}, {"a": {"x": 2}}])
    with pytest.raises(PlaceholderError, match="more than one result"):
        substitute("{{facts.a.x}}", index)
    named = FactIndex.from_facts([{"a": {"x": 1}}, {"a": {"x": 2}}], names=["first", "second"])
    assert substitute("{{facts.first.a.x}} and {{facts.second.a.x}}", named)[0] == "1 and 2"


# --------------------------------------------------------------------- compose


def test_a_clean_narration_sits_above_the_blocks_and_the_disclaimer_is_last():
    composed = compose(
        BLOCKS, "For {{facts.snapshot.selected_tax_year}} the credit is {{facts.credit.annual_credit_usd}}.",
        FACTS, CONTEXT,
    )
    assert composed.narration_used and composed.guard.status == PASS
    assert composed.text.startswith("For 2023 the credit is $3,500.")
    assert composed.text.endswith(DISCLAIMER)
    assert render_markdown(BLOCKS) in composed.text


@pytest.mark.parametrize("narration", [
    "Your credit is $3,500.",                       # a correct figure, typed
    "Your credit is $3,540.",                       # a wrong one
    "That is {{facts.credit.annual_credit_usd}} for 5 hires.",  # a stray figure beside a placeholder
    "About {{facts.credit.annual_credit_usd}}, or roughly 3.5K.",
    "There are five hundred and thirty nine, i.e. 539.",
    "\uff13\uff15\uff10\uff10 dollars",
])
def test_a_narrator_that_types_a_figure_loses_its_narration(narration):
    composed = compose(BLOCKS, narration, FACTS, CONTEXT)
    assert composed.guard.status == REJECTED
    assert composed.narration_used is False
    assert composed.text == BLOCKS_ONLY
    assert composed.guard.violations
    assert all(v.stage == "narration" for v in composed.guard.violations)


@pytest.mark.parametrize("narration", [
    "{{facts.credit.nope}}",
    "{{facts.credit.annual_credit_usd|accounting}}",
    "```\n{{facts.credit.annual_credit_usd}}\n```",
])
def test_an_unrenderable_placeholder_falls_back_rather_than_raising(narration):
    composed = compose(BLOCKS, narration, FACTS, CONTEXT)
    assert composed.guard.status == REJECTED and composed.narration_used is False
    assert composed.text == BLOCKS_ONLY
    assert composed.guard.violations[0].numeral.kind == "placeholder"


def test_the_readers_own_numbers_may_be_said_back():
    context = AllowedContext.build("what if we hire 5 people?", years=[2023])
    composed = compose(BLOCKS, "With 5 hires in TY2023, see {{facts.credit.annual_credit_usd}}.", FACTS, context)
    assert composed.narration_used, composed.guard.to_dict()


def test_with_no_narration_the_reply_is_the_blocks_and_the_disclaimer():
    for narration in (None, "", "   \n"):
        composed = compose(BLOCKS, narration, FACTS, CONTEXT)
        assert composed.text == BLOCKS_ONLY
        assert composed.narration_used is False and composed.guard.status == PASS


def test_the_disclaimer_is_on_every_reply():
    assert compose(BLOCKS, "A sentence.", FACTS, CONTEXT).text.endswith(DISCLAIMER)
    assert compose(BLOCKS, "Typed 539.", FACTS, CONTEXT).text.endswith(DISCLAIMER)
    assert compose([], None, FACTS, CONTEXT).text == DISCLAIMER


def test_a_rejection_never_patches_the_sentence():
    composed = compose(BLOCKS, "Roughly 540 people qualify.", FACTS, CONTEXT)
    assert "540" not in composed.text and "Roughly" not in composed.text
    assert composed.text == BLOCKS_ONLY


# ------------------------------------------------- defence in depth, and honesty


def test_a_formatter_that_prints_a_wrong_figure_is_caught_by_the_final_check(monkeypatch):
    """The raw gate trusts the formatter; the final gate does not."""
    broken = fmt.Formatter("money", "broken", lambda v: "$3,540", lambda v: ("$3,540",))
    monkeypatch.setitem(fmt.FORMATTERS, "money", broken)

    composed = compose(BLOCKS, "The credit is {{facts.credit.annual_credit_usd}}.", FACTS, CONTEXT)

    assert composed.guard.status == REJECTED and composed.narration_used is False
    assert composed.text == BLOCKS_ONLY
    assert any(v.stage == "final" and v.numeral.text == "$3,540" for v in composed.guard.violations)


def test_blocks_that_carry_a_figure_the_facts_do_not_are_withheld_with_a_notice():
    forged = [Block("paragraph", text="Annual credit: $9,999")]
    composed = compose(forged, "A sentence.", FACTS, CONTEXT)
    assert composed.blocks_verified is False and composed.guard.status == REJECTED
    assert "9,999" not in composed.text
    assert composed.notice and composed.notice in composed.text
    assert composed.text.endswith(DISCLAIMER)
    assert composed.cards_payload["body"] == []


def test_the_composer_depends_on_the_guard_being_consulted(monkeypatch):
    """Break a formatter, then take the guard away: the wrong figure goes out.

    With the real guard the narration is dropped (above). With one that approves
    everything the same broken reply is sent as if it were fine — which is the
    evidence that the rejection is the guard's doing and not an accident.
    """
    broken = fmt.Formatter("money", "broken", lambda v: "$3,540", lambda v: ("$3,540",))
    monkeypatch.setitem(fmt.FORMATTERS, "money", broken)
    narration = "The credit is {{facts.credit.annual_credit_usd}}."

    assert compose(BLOCKS, narration, FACTS, CONTEXT).narration_used is False

    monkeypatch.setattr(numeric_guard, "check", lambda text, **kwargs: GuardResult(PASS))
    monkeypatch.setattr(
        numeric_guard, "check_raw", lambda text, **kwargs: GuardResult(PASS),
    )
    unguarded = compose(BLOCKS, narration, FACTS, CONTEXT)
    assert unguarded.narration_used is True and "$3,540" in unguarded.text


def test_the_guard_runs_before_substitution_and_again_after(monkeypatch):
    calls: list[tuple[str, str]] = []
    real_check = numeric_guard.check

    def spy(text, **kwargs):
        calls.append((kwargs.get("stage", "final"), text))
        return real_check(text, **kwargs)

    monkeypatch.setattr(numeric_guard, "check", spy)
    compose(BLOCKS, "The credit is {{facts.credit.annual_credit_usd}}.", FACTS, CONTEXT)

    stages = [stage for stage, _ in calls]
    assert stages[0] == "narration" and "final" in stages
    raw_text = calls[0][1]
    assert "{{" not in raw_text and "3,500" not in raw_text, "the raw gate sees the narration before any figure is in it"
    final_text = next(text for stage, text in calls if stage == "final")
    assert "$3,500" in final_text


# --------------------------------------------------------------------- blocks


def test_blocks_render_to_markdown_without_adding_a_figure():
    md = render_markdown([
        Block("heading", text="Title"),
        Block("paragraph", text="A paragraph."),
        Block("bullets", rows=(("one",), ("two",))),
        Block("callout", text="Careful"),
        Block("table", rows=(("A", "B|C"), ("1", "2"))),
    ])
    assert md.splitlines()[0] == "### Title"
    assert "- one" in md and "- two" in md
    assert "> Careful" in md
    assert "| A | B\\|C |" in md and "| --- | --- |" in md


def test_cards_payload_is_neutral_structure_not_card_json():
    cards = composer.cards_payload(BLOCKS)
    assert cards["title"] == "Georgia Jobs Tax Credit"
    assert cards["disclaimer"] == DISCLAIMER
    kinds = [item["type"] for item in cards["body"]]
    assert kinds == ["facts", "paragraph"]
    assert cards["body"][0]["rows"][0] == ["Annual credit", "$3,500"]
    wide = composer.cards_payload([Block("table", rows=(("A", "B", "C"), ("1", "2", "3")))])
    assert wide["body"][0]["type"] == "table" and wide["body"][0]["columns"] == ["A", "B", "C"]
    assert "AdaptiveCard" not in repr(cards) and "$schema" not in repr(cards)


def test_a_composed_reply_serialises_for_the_audit_row():
    body = compose(BLOCKS, "Typed 539.", FACTS, CONTEXT).to_dict()
    assert body["guard"]["status"] == "rejected" and body["narration_used"] is False


# ------------------------------------------------------------------ vendoring


def test_the_composer_imports_only_the_standard_library_and_its_vendored_siblings():
    """The composer was split into `composer_*` siblings by size; the vendored set is all of them."""
    import sys

    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    local_prefixes = (
        "application.numeric_", "application.composer_", "application.output_policy",
        "application.capabilities.format", "application.capabilities.envelope",
    )
    root = Path(composer.__file__).parent
    for name in ("composer", "composer_placeholders", "composer_render"):
        found: set[str] = set()
        for node in ast.walk(ast.parse((root / f"{name}.py").read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.update(f"{node.module}.{a.name}" for a in node.names)
        bad = {m for m in found if m.split(".")[0] not in stdlib and not m.startswith(local_prefixes)
               and m != "application.numeric_guard" and not m.startswith("application.numeric_guard.")}
        assert not bad, f"{name} imports {sorted(bad)}"
