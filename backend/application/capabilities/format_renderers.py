"""The individual formatters: how each kind of figure prints, and every spelling the guard accepts. [ADR-008]

Each kind has a `_x_render` (the canonical spelling) and `_x_variants` (every
spelling the guard should accept, canonical first). Exact, never rounded: a
formatter may pad zeros or group digits; it never drops a digit. Split out of
`format`, which registers them and exposes the public API.

Standard library only: vendored with `format`.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from application.capabilities.format_core import (
    _ISO_DATE, _MONTHS, _body, _place_options, _signed, _split, _unique, to_decimal,
)


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
