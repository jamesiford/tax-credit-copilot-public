"""Canonical values and spelling helpers for the formatters. [ADR-008]

`to_decimal` is the one definition of "what number is this fact", and the small
helpers below split, group, pad and sign digits without ever dropping one. Split out
of `format` (which re-exports the public names) so each formatter module reads as
rules rather than plumbing.

Standard library only: vendored into the orchestrator container with `format`.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")

_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)


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
    """Whether `to_decimal` accepts `value`."""
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


@dataclass(frozen=True)
class Formatter:
    """One way to print a value, and every spelling of it the guard accepts."""

    name: str
    description: str
    render: Callable[[Any], str]
    variants: Callable[[Any], tuple[str, ...]]
