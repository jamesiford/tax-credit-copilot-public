"""The formatter prints exactly what the engine produced, and lists every spelling.

The numeric guard (ADR-008) accepts a figure only if it equals a fact or is a
spelling this module can emit, so these tests are the other half of that
contract: what is printed, what is accepted, and — as important — what is not.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from application.capabilities import format as fmt


@pytest.mark.parametrize("value, expected", [
    (3500, "$3,500"),
    ("3500", "$3,500"),
    (Decimal("3500.00"), "$3,500"),
    (3500.5, "$3,500.50"),
    ("77000", "$77,000"),
    (0, "$0"),
    (-3500, "-$3,500"),
    (1234567.89, "$1,234,567.89"),
    (Decimal("12.345"), "$12.345"),
])
def test_money(value, expected):
    assert fmt.money(value) == expected


@pytest.mark.parametrize("value, expected", [
    (10236, "10,236"), ("539", "539"), (0, "0"), (-3, "-3"), (Decimal("656"), "656"),
])
def test_count(value, expected):
    assert fmt.count(value) == expected


@pytest.mark.parametrize("value", [12.67, "0.5", Decimal("3")])
def test_count_refuses_a_figure_that_is_not_whole(value):
    if Decimal(str(value)) == Decimal(str(value)).to_integral_value():
        assert fmt.count(value)
    else:
        with pytest.raises(ValueError):
            fmt.count(value)


@pytest.mark.parametrize("value, expected", [
    (12.67, "12.67"), (99.0, "99.00"), (99, "99.00"), (0.58, "0.58"),
    (-0.83, "-0.83"), (1234.5, "1,234.50"), (12.345, "12.345"),
])
def test_headcount_never_drops_a_digit(value, expected):
    assert fmt.headcount(value) == expected


@pytest.mark.parametrize("value, expected", [
    (12.67, "12.67"), (1234.5, "1,234.5"), (7, "7"), (0.1 + 0.2, "0.30000000000000004"),
])
def test_number_prints_the_shortest_exact_decimal(value, expected):
    assert fmt.number(value) == expected


@pytest.mark.parametrize("ratio, expected", [(0.125, "12.5%"), (1, "100%"), (0.05, "5%"), (-0.2, "-20%")])
def test_percent_is_a_ratio_scaled_exactly(ratio, expected):
    assert fmt.percent(ratio) == expected


def test_percent_points_are_not_scaled():
    assert fmt.percent_points(12.5) == "12.5%"


@pytest.mark.parametrize("value, expected", [
    (2023, "2023"), ("2023", "2023"),
])
def test_year(value, expected):
    assert fmt.year(value) == expected


@pytest.mark.parametrize("value", [3500, 12.5, 12.67, 0, 1999.99])
def test_a_tax_year_must_look_like_one(value):
    with pytest.raises(ValueError):
        fmt.year(value)


@pytest.mark.parametrize("value", [
    "2023-07-28", date(2023, 7, 28), datetime(2023, 7, 28, 9, 30), "2023-07-28T09:30:00",
])
def test_date_is_iso(value):
    assert fmt.date_str(value) == "2023-07-28"
    assert "July 28, 2023" in fmt.render_variants(value, "date")


@pytest.mark.parametrize("value", [True, None, "GA_JTC", "12abc", "", float("nan"), float("inf")])
def test_a_non_number_is_refused_not_guessed_at(value):
    assert not fmt.is_number(value)
    with pytest.raises(ValueError):
        fmt.money(value)


# -------------------------------------------------------------------- variants


@pytest.mark.parametrize("formatter, value", [
    ("money", 3500), ("money", 3500.5), ("money", -3500), ("money", "77000"),
    ("compact_money", 3500), ("compact_money", 3540), ("compact_money", 1234567), ("compact_money", 900),
    ("count", 10236), ("number", 12.67), ("headcount", 12.67), ("headcount", 99),
    ("percent", 0.125), ("percent_points", 12.5), ("year", 2023), ("date", "2023-07-28"),
])
def test_the_canonical_rendering_is_always_its_first_variant(formatter, value):
    canonical = fmt.format_value(value, formatter)
    variants = fmt.render_variants(value, formatter)
    assert variants[0] == canonical
    assert len(set(variants)) == len(variants)


def test_money_variants_include_the_plain_forms_the_brief_names():
    variants = set(fmt.render_variants(3500, "money"))
    assert {"$3,500", "3,500", "3500", "$3,500.00"} <= variants
    assert "$3,500.5" not in variants and "$3,501" not in variants


def test_negative_money_has_both_conventional_spellings():
    variants = set(fmt.render_variants(-3500, "money"))
    assert {"-$3,500", "($3,500)", "-3,500", "(3,500)", "-3500"} <= variants


@pytest.mark.parametrize("value", [3500, 3540, 548730, 1_234_567, 2_500_000_000, -3500])
def test_compact_money_is_lossless(value):
    """`$3.5K` is exactly 3,500 and `$3.54K` exactly 3,540 — never "about"."""
    scale = {"K": Decimal(1000), "M": Decimal(10) ** 6, "B": Decimal(10) ** 9}
    for spelling in fmt.render_variants(value, "compact_money"):
        digits = spelling.lstrip("-(").replace("$", "").rstrip(")")
        if digits[-1] in scale:
            assert Decimal(digits[:-1]) * scale[digits[-1]] * (-1 if value < 0 else 1) == value


def test_a_rounded_abbreviation_is_not_a_variant_of_the_unrounded_figure():
    assert "$3.5K" in fmt.render_variants(3500, "compact_money")
    assert "$3.5K" not in fmt.numeric_variants(3540)
    assert "$3.54K" in fmt.numeric_variants(3540)


def test_a_figure_below_a_thousand_has_no_abbreviation():
    assert fmt.compact_money(900) == "$900"


def test_numeric_variants_skip_formatters_that_would_refuse():
    variants = fmt.numeric_variants(12.67)
    assert "12.67" in variants
    assert not any(v.startswith("TY") for v in variants), "12.67 is not a tax year"
    assert "13" not in variants and "12.7" not in variants, "rounding is never a variant"


def test_a_percentage_is_offered_only_on_a_hint():
    """A headcount of 0.125 is not 12.5%; the guard cannot tell without being told."""
    assert "12.5%" not in fmt.numeric_variants(0.125)
    assert "12.5%" in fmt.numeric_variants(0.125, percent_hint=True)


@pytest.mark.parametrize("path, value, expected", [
    ("credit.annual_credit_usd", 3500, "money"),
    ("snapshot.selected_tax_year", 2023, "year"),
    ("base_tax_year", 2020, "year"),
    ("credit.average_headcount", 12.67, "headcount"),
    ("credit.qualifying_jobs", 12.67, "number"),
    ("population.min_max_eligible", 539, "count"),
    ("snapshot.fiscal_window.begin", "2023-07-28", "date"),
    ("credit.citation", "O.C.G.A. 48-7-40.26", "text"),
    ("x.share_pct", 12.5, "percent_points"),
])
def test_a_bare_placeholder_picks_a_formatter_from_the_fact_not_the_magnitude(path, value, expected):
    assert fmt.infer_formatter(path, value) == expected


def test_an_unknown_formatter_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        fmt.get_formatter("accounting")


def test_every_formatter_is_documented():
    for name, formatter in fmt.FORMATTERS.items():
        assert formatter.name == name
        assert formatter.description.strip()
