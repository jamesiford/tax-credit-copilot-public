"""The numeric guard: zero tolerance for a figure the engine did not produce.

Organised by what the guard promises:

* it accepts every spelling a formatter can emit, and only those;
* it rejects a changed digit, a dropped decimal, a transposition, an invented
  figure, a rounded or abbreviated figure nobody emitted, and any digit that is
  not an ASCII digit or is split by a space-like character;
* it accepts the reader's own numerals and structural digits, narrowly;
* and it is actually consulted — a mutation test flips one digit of every
  numeral in a valid reply, and a meta-test proves that test fails when the guard
  is replaced by one that always passes.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from application import composer
from application.numeric import guard as numeric_guard
from application.capabilities import format as fmt
from application.capabilities.envelope import Block
from application.numeric.guard import (
    AllowedContext,
    FactIndex,
    GuardResult,
    PASS,
    REJECTED,
    check,
    check_raw,
    extract_numerals,
)

FACTS = {
    "credit": {
        "credit_name": "Georgia Jobs Tax Credit",
        "citation": "O.C.G.A. 48-7-40.26",
        "annual_credit_usd": 3500,
        "lifetime_credit_usd": 17500,
        "average_headcount": 12.67,
        "prior_period_average_headcount": 10.01,
        "benefit_period_years": 5,
    },
    "population": {"employees_evaluated": 10236, "min_max_eligible": 539, "pay_period_eligible": 656},
    "snapshot": {
        "selected_tax_year": 2023,
        "fiscal_window": {"begin": "2023-07-28", "end": "2024-08-02"},
    },
    "totals": {"identified_usd": "548730.50", "share_ratio": 0.125, "owed_usd": -1200},
    "margin": {"jobs_margin": -0.83},
}


@pytest.fixture
def index() -> FactIndex:
    return FactIndex.from_facts(FACTS, percent_paths=["totals.share_ratio"])


def _passes(text: str, index: FactIndex, context: AllowedContext | None = None) -> bool:
    return check(text, facts=index, allowed_context=context).passed


# ------------------------------------------------------------------- extraction


@pytest.mark.parametrize("text, kind, value", [
    ("$1,234.56", "money", "1234.56"),
    ("1234", "number", "1234"),
    ("1,234", "number", "1234"),
    ("12.5", "number", "12.5"),
    (".5", "number", "0.5"),
    ("-3", "number", "-3"),
    ("(3)", "number", "-3"),
    ("($3,500)", "money", "-3500"),
    ("-$3,500", "money", "-3500"),
    ("12%", "percent", "12"),
    ("12 percent", "percent", "12"),
    ("$1.2M", "abbreviated", "1200000"),
    ("$3.5K", "abbreviated", "3500"),
    ("1.2 million", "abbreviated", "1200000"),
    ("2.5 billion", "abbreviated", "2500000000"),
    ("TY2023", "year", "2023"),
    ("2023-07-28", "date", None),
    ("2023-07-28T09:30:00Z", "date", None),
])
def test_each_shape_is_recognised_whole(text, kind, value):
    found = extract_numerals(f"It is {text} today")
    assert len(found) == 1, found
    assert found[0].kind == kind
    assert found[0].text == text
    assert (found[0].value is None) if value is None else (found[0].value == Decimal(value))


def test_a_range_is_two_numerals_not_a_negative():
    assert [n.value for n in extract_numerals("between 3–5 jobs")] == [Decimal(3), Decimal(5)]
    assert [n.value for n in extract_numerals("between 3-5 jobs")] == [Decimal(3), Decimal(5)]
    assert [n.value for n in extract_numerals("Q3-24")] == [Decimal(3), Decimal(24)]


def test_a_number_beside_a_unit_is_still_a_number():
    assert [n.value for n in extract_numerals("12.67 FTE across 14 jobs")] == [Decimal("12.67"), Decimal(14)]


def test_number_words_are_not_numerals():
    assert extract_numerals("twelve jobs and one hundred hours") == []


def test_a_parenthesis_that_is_not_a_negative_is_just_punctuation():
    found = extract_numerals("(see 3 below)")
    assert found[0].value == Decimal(3) and found[0].text == "3"


def test_structural_digits_are_the_narrow_list():
    text = "1. First\n2) Second\n  - 3. Third\nstep 4 of the plan, the 1st and 10th"
    kinds = {n.text: n.kind for n in extract_numerals(text)}
    assert kinds["1"] == kinds["2"] == kinds["3"] == kinds["4"] == "structural"
    assert kinds["1st"] == kinds["10th"] == "ordinal"
    assert extract_numerals("539. That is the count")[0].kind == "number"
    assert extract_numerals("the 11th hire")[0].kind == "ordinal"


# ------------------------------------------------------------- what it accepts


def _numeric_leaves():
    from application.numeric.guard import _flatten

    flat: dict = {}
    _flatten("", FACTS, flat)
    return [(path, value) for path, value in flat.items() if fmt.is_number(value) and not isinstance(value, bool)]


@pytest.mark.parametrize("path, value", _numeric_leaves(), ids=lambda p: str(p))
def test_every_spelling_the_formatter_can_emit_passes(path, value, index):
    spellings = fmt.numeric_variants(value, percent_hint=path == "totals.share_ratio")
    assert spellings
    for spelling in sorted(spellings):
        assert _passes(f"The figure is {spelling}.", index), (path, spelling)


@pytest.mark.parametrize("formatter, value", [
    ("money", 3500), ("compact_money", 3500), ("count", 539), ("headcount", 12.67),
    ("year", 2023), ("percent", 0.125), ("date", "2023-07-28"),
])
def test_the_rendering_a_formatter_prints_always_passes(formatter, value, index):
    assert _passes(fmt.format_value(value, formatter), index), formatter


def test_a_money_figure_serialised_as_a_string_is_the_same_figure(index):
    assert _passes("$548,730.50", index)
    assert _passes("548730.5", index)
    assert not _passes("$548,730", index)


def test_digits_inside_a_string_fact_are_the_engines_own(index):
    """A citation is the engine's text; its digits are not a figure a model made up."""
    assert _passes("per O.C.G.A. 48-7-40.26", index)
    assert not _passes("per O.C.G.A. 48-7-40.27", index)


def test_the_reader_s_own_numerals_are_accepted(index):
    context = AllowedContext.build("What if we hired 5 people in Atlanta in 2025?", years=[2025], numbers=[2001])
    assert _passes("Hiring 5 people in 2025 for client 2001.", index, context)
    assert not _passes("Hiring 6 people in 2025.", index, context)


def test_scope_years_and_ids_are_passed_explicitly_never_inferred(index):
    assert not _passes("TY2024", index)
    assert _passes("TY2024", index, AllowedContext.build(years=[2024]))


def test_a_percentage_the_reader_wrote_is_theirs(index):
    context = AllowedContext.build("is 7% realistic?")
    assert _passes("7%", index, context)
    assert not _passes("7", index, context) or Decimal(7) in index.values  # 7 is a fact digit here
    assert not _passes("8%", index, context)


def test_a_date_must_be_a_fact_or_the_readers(index):
    assert _passes("from 2023-07-28 to 2024-08-02", index)
    assert not _passes("from 2023-07-29", index)
    assert _passes("on 2023-09-01", index, AllowedContext.build("what happened on 2023-09-01?"))


def test_list_markers_and_small_ordinals_are_structural(index):
    assert _passes("1. First point\n2. Second point\n3. Third point", index)
    assert _passes("In the 1st year, then the 5th.", index)
    assert _passes("step 2 is next", index)
    assert not _passes("In the 11th year", index)


def test_text_with_no_numerals_passes_trivially(index):
    result = check("Nothing to report here.", facts=index)
    assert result.status == PASS and result.violations == ()


def test_the_decimal_equality_is_exact_not_numeric_closeness(index):
    assert _passes("12.67", index) and _passes("12.670", index) and _passes("12.6700", index)
    assert not _passes("12.671", index)
    assert not _passes("12.66", index)


# ------------------------------------------------------------- what it rejects


@pytest.mark.parametrize("text", [
    "$3,540",            # a changed digit
    "12",                # a dropped decimal (12.67)
    "12.7",              # a rounded figure
    "13",                # a rounded figure
    "$5,300",            # a transposition of $3,500
    "10,263",            # a transposition of 10,236
    "42",                # an extra figure nobody supplied
    "$17,501",           # off by one
    "-$3,500",           # a sign the fact does not carry
    "(539)",             # a positive count shown as a negative
    "0.83",              # a negative margin shown positive
    "50%",               # a percentage not in the facts
    "13%",               # a close percentage
    "TY2024",            # a year nobody supplied
    "2023-07-29",        # a date nobody supplied
])
def test_a_wrong_figure_is_rejected(text, index):
    result = check(f"The answer is {text}.", facts=index)
    assert result.status == REJECTED, text
    assert result.violations


def test_a_ratio_is_not_a_percentage_unless_it_was_said_to_be():
    plain = FactIndex.from_facts({"x": {"share_ratio": 0.125}})
    assert not _passes("12.5%", plain)
    assert _passes("12.5%", plain.with_percent("x.share_ratio"))
    assert not _passes("12.5%", FactIndex.from_facts({"headcount": 0.125}))


def test_an_abbreviation_is_rejected_unless_the_formatter_emitted_exactly_it():
    index = FactIndex.from_facts({"owed_usd": 3540})
    assert not _passes("about $3.5K", index)
    assert not _passes("roughly $4K", index)
    assert not _passes("$3.5k", index)
    assert _passes("$3.54K", index)
    assert _passes("$3,540", index)
    assert not _passes("$0.0035 million", index)
    # Millions start at 1,000,000; nobody emits $0.00354 million for 3,540.
    assert not _passes("$0.00354 million", index)


@pytest.mark.parametrize("text", [
    "\uff13\uff15\uff10\uff10",     # full-width digits for 3500
    "\u0663\u0665\u0660\u0660",     # Arabic-Indic digits
    "\u00bd",                       # a vulgar fraction
    "\u00b2",                       # a superscript
])
def test_a_character_that_looks_like_a_digit_is_rejected_not_normalised(text):
    index = FactIndex.from_facts({"a": 3500})
    result = check(f"value {text}", facts=index)
    assert result.status == REJECTED
    assert any(v.numeral.kind == "non_ascii" for v in result.violations)


@pytest.mark.parametrize("separator", ["\u2009", "\u00a0", "\u202f", "\u2007", "\u200b"])
def test_a_figure_split_by_a_thin_or_no_break_space_is_rejected(separator):
    """`3 500` is 3,500 to a reader and two small numbers to a naive guard."""
    index = FactIndex.from_facts({"a": 3500, "b": 3, "c": 500})
    result = check(f"value 3{separator}500", facts=index)
    assert result.status == REJECTED
    assert len(result.violations) == 1 and result.violations[0].numeral.kind == "non_ascii"


def test_two_numbers_split_by_an_ordinary_space_are_judged_separately():
    index = FactIndex.from_facts({"a": 3500})
    assert not _passes("3 500", index)
    assert _passes("3 500", FactIndex.from_facts({"a": 3, "b": 500}))


def test_digits_inside_a_code_fence_are_still_figures():
    index = FactIndex.from_facts({"a": 3540})
    assert not _passes("```\n3500\n```", index)
    assert _passes("```\n3540\n```", index)


def test_a_violation_names_the_nearest_fact_so_a_changed_digit_is_obvious(index):
    result = check("$3,540", facts=index)
    violation = result.violations[0]
    assert violation.numeral.text == "$3,540"
    assert violation.nearest == Decimal(3500)
    assert violation.reason
    assert result.to_dict()["violations"][0]["nearest_fact"] == "3500"


def test_the_guard_result_serialises_for_the_audit_row(index):
    body = check("42 and $3,540", facts=index).to_dict()
    assert body["status"] == "rejected"
    assert {v["numeral"]["text"] for v in body["violations"]} == {"42", "$3,540"}
    assert check("$3,500", facts=index).to_dict() == {"status": "pass", "violations": []}


# --------------------------------------------------------- the model's own words


def test_a_digit_the_model_typed_is_rejected_even_when_it_equals_a_fact():
    """The narrator is told never to write a figure. One that does is producing a number."""
    assert check_raw("Your credit is $3,500.").status == REJECTED
    assert check_raw("There are 539 eligible employees.").status == REJECTED


def test_the_models_words_may_carry_the_readers_numbers_and_structure():
    context = AllowedContext.build("what about 5 hires in 2025?", years=[2025])
    assert check_raw("For 5 hires in 2025:\n1. First\n2. Second", allowed_context=context).passed
    assert not check_raw("For 6 hires in 2025", allowed_context=context).passed


def test_prose_with_no_digits_passes_the_raw_gate():
    assert check_raw("The credit below comes straight from the engine.").passed


# ------------------------------------------------------------- the guard is used


def _valid_reply():
    blocks = [
        Block("heading", text="Georgia Jobs Tax Credit"),
        Block("table", rows=(
            ("Measure", "Value"),
            ("Annual credit", fmt.money(3500)),
            ("Lifetime credit", fmt.money(17500)),
            ("Average headcount", fmt.headcount(12.67)),
            ("Eligible employees", fmt.count(539)),
            ("Window", f"{fmt.date_str('2023-07-28')} to {fmt.date_str('2024-08-02')}"),
        )),
        Block("paragraph", text="Citation: O.C.G.A. 48-7-40.26"),
    ]
    narration = (
        "For {{facts.snapshot.selected_tax_year|year}} the annual credit is "
        "{{facts.credit.annual_credit_usd}} on an average headcount of "
        "{{facts.credit.average_headcount}}, and {{facts.totals.share_ratio|percent}} of the pool is shown below."
    )
    context = AllowedContext.build(years=[2023])
    index = FactIndex.from_facts(FACTS, percent_paths=["totals.share_ratio"])
    composed = composer.compose(blocks, narration, index, context)
    assert composed.narration_used, composed.guard.to_dict()
    return composed.text, index, composed, context


def _mutations(text: str, accept):
    """Every single-digit corruption of every numeral, each of which must be refused.

    For each digit position, take the first replacement digit that does not turn
    the numeral into another legitimate value: a corruption that happens to land
    on a different fact is a coincidence, not a defect of the guard.
    """
    known = set(accept["values"])
    for numeral in extract_numerals(text):
        if numeral.kind in {"structural", "ordinal", "non_ascii"}:
            continue
        for offset, char in enumerate(numeral.text):
            if not char.isdigit():
                continue
            position = numeral.start + offset
            for replacement in "0123456789":
                if replacement == char:
                    continue
                mutated = text[:position] + replacement + text[position + 1:]
                again = [n for n in extract_numerals(mutated) if n.start <= position < n.end]
                if numeral.kind == "date":
                    if again and again[0].text not in accept["dates"]:
                        yield numeral, mutated
                        break
                    continue
                if again and again[0].value not in known and again[0].kind != "structural":
                    yield numeral, mutated
                    break


def _assert_every_mutation_is_refused(check_fn) -> int:
    text, index, _composed, context = _valid_reply()
    accept = {"values": set(index.values) | set(context.values) | set(context.percents), "dates": set(index.dates)}
    count = 0
    for numeral, mutated in _mutations(text, accept):
        count += 1
        result = check_fn(mutated, index, context)
        assert result.status == REJECTED, f"{numeral.text!r} -> {mutated!r} was accepted"
    return count


def test_flipping_any_digit_of_any_numeral_in_a_valid_reply_is_refused():
    count = _assert_every_mutation_is_refused(
        lambda text, index, context: numeric_guard.check(text, facts=index, allowed_context=context)
    )
    assert count >= 30, f"only {count} mutations ran; the loop is not exercising the reply"


def test_the_mutation_test_fails_if_the_guard_is_not_consulted(monkeypatch):
    """A test that passes with and without the guard proves nothing.

    Replace the guard with one that approves everything: the mutation loop must
    then fail, which is the evidence that the passing run above depends on it.
    """
    monkeypatch.setattr(numeric_guard, "check", lambda text, **kwargs: GuardResult(PASS))
    with pytest.raises(AssertionError, match="was accepted"):
        _assert_every_mutation_is_refused(
            lambda text, index, context: numeric_guard.check(text, facts=index, allowed_context=context)
        )


def test_the_valid_reply_really_is_valid():
    text, index, composed, context = _valid_reply()
    assert numeric_guard.check(text, facts=index, allowed_context=context).passed
    for expected in ("$3,500", "12.67", "12.5%", "2023"):
        assert expected in text
    assert composed.guard.passed


# ------------------------------------------------------------------ vendoring


def _imports(path: Path) -> set[str]:
    """What a file imports, as dotted targets: `from a import b` is `a.b`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def test_the_guard_imports_only_the_standard_library_and_the_formatter():
    """It is vendored into the orchestrator container, which has no repository.

    The guard lives with its parts in `application.numeric`; the vendored set is all of
    them, and each may import only the standard library, the formatter, or a sibling.
    """
    import sys

    modules = ("__init__", "guard", "types", "extract", "context", "facts")
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    root = Path(numeric_guard.__file__).parent
    imported: set[str] = set()
    for name in modules:
        found = _imports(root / f"{name}.py")
        imported |= found
        bad = {m for m in found if m.split(".")[0] not in stdlib
               and m != "application.capabilities.format" and not m.startswith("application.numeric")}
        assert not bad, f"{name} imports {sorted(bad)}"
    assert "application.capabilities.format" in imported
