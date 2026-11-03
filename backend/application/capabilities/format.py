"""The single formatter for every figure the platform renders into text.

Every number that reaches a reader in a `ToolResult.blocks` goes through here,
and the numeric guard (ADR-008) accepts exactly the renderings this module can
emit — nothing looser. That is the contract: a figure is correct if the engine
produced it, and it is *shown* correctly if one of these formatters printed it.

Two rules shape the module:

* **Exact, never rounded.** A formatter may pad zeros or group digits; it never
  drops a digit. `12.67` is `12.67`, not `13` and not `12.7`. Rounding is the
  engine's decision, taken once, where the figure is computed.
* **Every formatter lists its variants.** `variants(value)` returns each
  spelling the guard should accept for that value (`$3,500`, `3,500`, `3500`,
  `$3,500.00`, …), canonical first. A spelling not in the list is rejected, so
  `about $3.5K` for 3,540 cannot slip through as a "close enough" rendering.

**Where the pieces live.** This module registers the formatters and is the public
API. The canonical-value helpers are in `format_core` and the individual formatters
in `format_renderers`; both were split out by size and are standard library only, so
every import of `application.capabilities.format` is unchanged.

Standard library only: this file and its siblings are vendored into the
orchestrator container.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from application.capabilities.format_core import (  # noqa: F401 - re-exported
    _ISO_DATE, Formatter, is_number, to_decimal,
)
from application.capabilities.format_renderers import (
    _compact_render, _compact_variants, _count_render, _count_variants, _date_render, _date_variants,
    _headcount_render, _headcount_variants, _money_render, _money_variants, _number_render,
    _number_variants, _percent_render, _percent_variants, _points_render, _points_variants,
    _text_render, _year_render, _year_variants,
)

FORMATTERS: dict[str, Formatter] = {
    f.name: f
    for f in (
        Formatter("money", "US dollars, whole when whole: $3,500 · $3,500.50", _money_render, _money_variants),
        Formatter("compact_money", "Lossless abbreviation: $3.5K · $1.2M", _compact_render, _compact_variants),
        Formatter("count", "A whole number: 10,236", _count_render, _count_variants),
        Formatter("number", "An exact decimal, grouped: 1,234.5", _number_render, _number_variants),
        Formatter("headcount", "FTE decimals, at least two places: 12.67 · 99.00", _headcount_render, _headcount_variants),
        Formatter("percent", "A ratio as a percentage: 0.125 -> 12.5%", _percent_render, _percent_variants),
        Formatter("percent_points", "A value already in percent: 12.5 -> 12.5%", _points_render, _points_variants),
        Formatter("year", "A tax year: 2023", _year_render, _year_variants),
        Formatter("date", "An ISO date: 2023-07-28", _date_render, _date_variants),
        Formatter("text", "Verbatim text", _text_render, lambda v: (str(v),)),
    )
}

#: Formatters that print a numeral. `text` and `date` are excluded: a date is
#: recognised by the guard as a unit, not as three loose numbers.
NUMERIC_FORMATTERS: tuple[str, ...] = (
    "money", "compact_money", "count", "number", "headcount", "year",
)
PERCENT_FORMATTERS: tuple[str, ...] = ("percent", "percent_points")


def get_formatter(name: str) -> Formatter:
    """The registered formatter, or a `KeyError` that lists the known names."""
    try:
        return FORMATTERS[name]
    except KeyError:
        raise KeyError(f"unknown formatter {name!r}; known: {', '.join(sorted(FORMATTERS))}") from None


def format_value(value: Any, name: str) -> str:
    """`value` printed by the named formatter."""
    return get_formatter(name).render(value)


def money(value: Any) -> str:
    """`value` as US dollars."""
    return _money_render(value)


def compact_money(value: Any) -> str:
    """`value` as a lossless abbreviation: $3.5K."""
    return _compact_render(value)


def count(value: Any) -> str:
    """`value` as a whole number."""
    return _count_render(value)


def number(value: Any) -> str:
    """`value` as an exact grouped decimal."""
    return _number_render(value)


def headcount(value: Any) -> str:
    """`value` as FTE decimals, at least two places."""
    return _headcount_render(value)


def percent(ratio: Any) -> str:
    """A ratio as a percentage: 0.125 prints as 12.5%."""
    return _percent_render(ratio)


def percent_points(points: Any) -> str:
    """A value already in percent: 12.5 prints as 12.5%."""
    return _points_render(points)


def year(value: Any) -> str:
    """`value` as a tax year."""
    return _year_render(value)


def date_str(value: Any) -> str:
    """`value` as an ISO date."""
    return _date_render(value)


def render_variants(value: Any, formatter: str) -> tuple[str, ...]:
    """Every spelling `formatter` may print for `value`, canonical first."""
    return get_formatter(formatter).variants(value)


def numeric_variants(value: Any, *, percent_hint: bool = False) -> frozenset[str]:
    """Every spelling any numeric formatter could print for `value`.

    Formatters that cannot take the value (`count` of 12.67) are skipped rather
    than raised, because the guard asks "could this have been printed?" and the
    honest answer for a formatter that would refuse is no. Percent spellings are
    offered only on a hint: a headcount of 0.125 is not 12.5%, and the guard
    cannot tell them apart without being told.
    """
    names = NUMERIC_FORMATTERS + (PERCENT_FORMATTERS if percent_hint else ())
    out: set[str] = set()
    for name in names:
        try:
            out.update(render_variants(value, name))
        except ValueError:
            continue
    return frozenset(out)


def infer_formatter(path: str, value: Any) -> str:
    """The formatter a bare `{{facts.path}}` placeholder uses.

    Inferred from the fact's name and type, never from its magnitude, so the
    same field always prints the same way. Anything ambiguous falls to `number`,
    which prints exactly the digits the engine produced.
    """
    leaf = path.rsplit(".", 1)[-1].lower()
    if isinstance(value, (date, datetime)) or (isinstance(value, str) and _ISO_DATE.match(value.strip())):
        return "date"
    if not is_number(value):
        return "text"
    if leaf.endswith(("_usd", "_dollars", "_amount")):
        return "money"
    if leaf in {"tax_year", "year", "base_tax_year", "lead_tax_year"} or leaf.endswith("_tax_year"):
        return "year"
    if "headcount" in leaf or leaf.endswith("_fte"):
        return "headcount"
    if leaf.endswith(("_pct", "_percent")):
        return "percent_points"
    if isinstance(value, int) and not isinstance(value, bool):
        return "count"
    return "number"
