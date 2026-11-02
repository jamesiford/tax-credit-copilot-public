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

Standard library only: this file is vendored into the orchestrator container.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")

_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)


# --------------------------------------------------------------- canonical value


def to_decimal(value: Any) -> Decimal:
    """The canonical numeric value of a fact, or `ValueError` if it is not one.

    Floats go through `repr`, which is the shortest string that round-trips, so
    `12.67` stays `12.67` rather than becoming `12.6699999999999999289…`. Strings
    count only when they are a bare number: `"77000"` is a money figure the
    claims layer serialised, `"GA_JTC"` is not.
    """
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        number = Decimal(repr(value))
    elif isinstance(value, str) and _PLAIN_NUMBER.match(value.strip()):
        number = Decimal(value.strip())
    else:
        raise ValueError(f"not a number: {value!r}")
    if not number.is_finite():
        raise ValueError(f"not a finite number: {value!r}")
    return number


def is_number(value: Any) -> bool:
    try:
        to_decimal(value)
    except ValueError:
        return False
    return True


def _split(value: Any) -> tuple[bool, str, str]:
    """`(negative, whole digits, fraction digits)`, exact, with no exponent."""
    number = to_decimal(value).normalize()
    text = format(number, "f")
    negative = text.startswith("-") and number != 0
    whole, _, fraction = text.lstrip("-").partition(".")
    return negative, whole, fraction


def _body(whole: str, fraction: str, *, places: int, grouped: bool) -> str:
    fraction = fraction.ljust(places, "0")
    digits = f"{int(whole):,}" if grouped else whole
    return digits + (f".{fraction}" if fraction else "")


def _place_options(fraction: str) -> range:
    """Decimal places a spelling may carry: as many as the value has, up to two
    more than a bare integer would show. Padding zeros is exact; dropping a
    digit is not, so the lower bound is the value's own precision."""
    return range(len(fraction), max(len(fraction), 2) + 1)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _signed(negative: bool, spellings: Iterable[str], *, parens: bool = True) -> list[str]:
    out: list[str] = []
    for spelling in spellings:
        if not negative:
            out.append(spelling)
            continue
        out.append(f"-{spelling}")
        if parens:
            out.append(f"({spelling})")
    return out


# ----------------------------------------------------------------- the formatters


@dataclass(frozen=True)
class Formatter:
    """One way to print a value, and every spelling of it the guard accepts."""

    name: str
    description: str
    render: Callable[[Any], str]
    variants: Callable[[Any], tuple[str, ...]]


def _money_render(value: Any) -> str:
    negative, whole, fraction = _split(value)
    places = 0 if not fraction else max(len(fraction), 2)
    return ("-" if negative else "") + "$" + _body(whole, fraction, places=places, grouped=True)


def _money_variants(value: Any) -> tuple[str, ...]:
    negative, whole, fraction = _split(value)
    bodies: list[str] = []
    for places in _place_options(fraction):
        for grouped in (True, False):
            bodies.append(_body(whole, fraction, places=places, grouped=grouped))
    with_symbol = [f"${b}" for b in bodies]
    return _unique([_money_render(value), *_signed(negative, with_symbol), *_signed(negative, bodies)])


_COMPACT_UNITS = (
    (9, "B", "billion"),
    (6, "M", "million"),
    (3, "K", "thousand"),
)


def _compact_parts(value: Any) -> tuple[bool, str, str, str] | None:
    """`(negative, scaled digits, short unit, long unit)`, or None below 1,000.

    Lossless by construction: scaling moves the decimal point and nothing else,
    so `$3.5K` is exactly 3,500 and `$3.54K` is exactly 3,540. The guard never
    has to decide whether an abbreviation is "close enough".
    """
    number = to_decimal(value)
    for power, short, long in _COMPACT_UNITS:
        if abs(number) >= Decimal(10) ** power:
            scaled = number.scaleb(-power)
            negative, whole, fraction = _split(scaled)
            return negative, whole + (f".{fraction}" if fraction else ""), short, long
    return None


def _compact_render(value: Any) -> str:
    parts = _compact_parts(value)
    if parts is None:
        return _money_render(value)
    negative, digits, short, _long = parts
    return f"{'-' if negative else ''}${digits}{short}"


def _compact_variants(value: Any) -> tuple[str, ...]:
    parts = _compact_parts(value)
    if parts is None:
        return _money_variants(value)
    negative, digits, short, long = parts
    spellings = [f"${digits}{short}", f"{digits}{short}", f"${digits} {long}", f"{digits} {long}"]
    return _unique(_signed(negative, spellings))


def _require_integer(value: Any) -> Decimal:
    number = to_decimal(value)
    if number != number.to_integral_value():
        raise ValueError(f"not a whole number: {value!r}")
    return number


def _count_render(value: Any) -> str:
    negative, whole, _ = _split(_require_integer(value))
    return ("-" if negative else "") + _body(whole, "", places=0, grouped=True)


def _count_variants(value: Any) -> tuple[str, ...]:
    negative, whole, _ = _split(_require_integer(value))
    bodies = [_body(whole, "", places=0, grouped=g) for g in (True, False)]
    return _unique(_signed(negative, bodies))


def _number_render(value: Any) -> str:
    negative, whole, fraction = _split(value)
    return ("-" if negative else "") + _body(whole, fraction, places=len(fraction), grouped=True)


def _number_variants(value: Any) -> tuple[str, ...]:
    negative, whole, fraction = _split(value)
    bodies = [
        _body(whole, fraction, places=p, grouped=g)
        for p in _place_options(fraction) for g in (True, False)
    ]
    return _unique([_number_render(value), *_signed(negative, bodies)])


def _headcount_render(value: Any) -> str:
    negative, whole, fraction = _split(value)
    return ("-" if negative else "") + _body(
        whole, fraction, places=max(len(fraction), 2), grouped=True
    )


def _headcount_variants(value: Any) -> tuple[str, ...]:
    negative, whole, fraction = _split(value)
    bodies = [
        _body(whole, fraction, places=p, grouped=g)
        for p in _place_options(fraction) for g in (True, False)
    ]
    return _unique([_headcount_render(value), *_signed(negative, bodies)])


def _percent_of(ratio: bool) -> tuple[Callable[[Any], str], Callable[[Any], tuple[str, ...]]]:
    def scaled(value: Any) -> Decimal:
        number = to_decimal(value)
        return number.scaleb(2) if ratio else number

    def render(value: Any) -> str:
        negative, whole, fraction = _split(scaled(value))
        return ("-" if negative else "") + _body(whole, fraction, places=len(fraction), grouped=True) + "%"

    def variants(value: Any) -> tuple[str, ...]:
        negative, whole, fraction = _split(scaled(value))
        bodies = [
            _body(whole, fraction, places=p, grouped=g) + "%"
            for p in _place_options(fraction) for g in (True, False)
        ]
        return _unique([render(value), *_signed(negative, bodies)])

    return render, variants


_percent_render, _percent_variants = _percent_of(ratio=True)
_points_render, _points_variants = _percent_of(ratio=False)


def _year_render(value: Any) -> str:
    year = int(_require_integer(value))
    if not 1900 <= year <= 2100:
        raise ValueError(f"not a tax year: {value!r}")
    return str(year)


def _year_variants(value: Any) -> tuple[str, ...]:
    year = _year_render(value)
    return _unique([year, f"TY{year}"])


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    match = _ISO_DATE.match(str(value).strip())
    if not match:
        raise ValueError(f"not a date: {value!r}")
    return date(int(match[1]), int(match[2]), int(match[3]))


def _date_render(value: Any) -> str:
    return _as_date(value).isoformat()


def _date_variants(value: Any) -> tuple[str, ...]:
    d = _as_date(value)
    month = _MONTHS[d.month - 1]
    return _unique([
        d.isoformat(),
        f"{month} {d.day}, {d.year}",
        f"{month[:3]} {d.day}, {d.year}",
        f"{d.day} {month} {d.year}",
    ])


def _text_render(value: Any) -> str:
    return str(value)


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
    try:
        return FORMATTERS[name]
    except KeyError:
        raise KeyError(f"unknown formatter {name!r}; known: {', '.join(sorted(FORMATTERS))}") from None


def format_value(value: Any, name: str) -> str:
    return get_formatter(name).render(value)


def money(value: Any) -> str:
    return _money_render(value)


def compact_money(value: Any) -> str:
    return _compact_render(value)


def count(value: Any) -> str:
    return _count_render(value)


def number(value: Any) -> str:
    return _number_render(value)


def headcount(value: Any) -> str:
    return _headcount_render(value)


def percent(ratio: Any) -> str:
    return _percent_render(ratio)


def percent_points(points: Any) -> str:
    return _points_render(points)


def year(value: Any) -> str:
    return _year_render(value)


def date_str(value: Any) -> str:
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
