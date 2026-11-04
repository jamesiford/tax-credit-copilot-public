"""Find every figure in a piece of text. [ADR-008]

`extract_numerals` is the one place that decides what counts as a numeral and what
it claims to be (money, percent, abbreviation, ordinal, year, date, structural, or a
non-ASCII digit that no formatter emits). The guard judges what this finds; it does
not re-read the text. Split out of `guard`, which re-exports everything here.

Standard library only (plus the sibling `types`): vendored with the guard.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from application.numeric.types import Numeral

#: The structural allow-list, deliberately narrow. These digits organise text and
#: carry no figure: a list marker at the start of a line (`1.` / `2)`), a step
#: number (`step 3`) and a small ordinal (`1st` to `10th`). Anything larger is a
#: number and must be a fact.
MAX_LIST_MARKER = 99
MAX_STEP = 20
MAX_ORDINAL = 10

_NO_BREAK_SPACES = "\u00a0\u2007\u2009\u202f\u200a\u2008\u2002\u2003\u2004\u2005\u2006\u200b"

_TOKEN = re.compile(
    r"""
      (?P<date>(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)
               (?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?)
    | (?P<ty>(?<![A-Za-z])(?:TY|FY|CY)[ ]?(?P<tyyear>\d{4})(?!\d))
    | (?P<num>(?:\d{1,3}(?:[,]\d{3})+(?!\d)|\d+)(?:\.\d+)?|(?<![\d.])\.\d+)
    """,
    re.VERBOSE | re.ASCII,
)

#: What may precede a number: `(`, a sign, a currency symbol, another sign.
_PREFIX = re.compile(r"(\()?([-\u2212\u2013+])?([$£€])?([-\u2212\u2013])?$")
_SPLIT_SPACES = re.compile(rf"\d[{_NO_BREAK_SPACES}]+\d", re.ASCII)
_SUFFIX_LONG = re.compile(r"[ ]?(thousand|million|billion|trillion)\b", re.IGNORECASE | re.ASCII)
_SUFFIX_SHORT = re.compile(r"(?:bn|mn|[KkMmBbTt])(?![A-Za-z])", re.ASCII)
_PERCENT = re.compile(r"[ ]?(?:%|percent\b|per cent\b)", re.IGNORECASE | re.ASCII)
_ORDINAL = re.compile(r"(?:st|nd|rd|th)\b", re.IGNORECASE | re.ASCII)
_LIST_LEAD = re.compile(r"^\s*(?:[-*>\u2022]\s*)?$")
_STEP_LEAD = re.compile(r"\bstep\s+$", re.IGNORECASE | re.ASCII)

_SCALE = {"k": 3, "thousand": 3, "m": 6, "mn": 6, "million": 6, "b": 9, "bn": 9, "billion": 9, "t": 12, "trillion": 12}


def _number_value(core: str) -> Decimal:
    return Decimal(core.replace(",", ""))


def _line_before(text: str, start: int) -> str:
    return text[text.rfind("\n", 0, start) + 1:start]


def extract_numerals(text: str) -> list[Numeral]:
    """Every figure in `text`, in order, with what it claims to be."""
    found: list[Numeral] = []

    for index, char in enumerate(text):
        category = unicodedata.category(char)
        if category in {"Nd", "No", "Nl"} and not ("0" <= char <= "9"):
            found.append(Numeral(char, index, index + 1, "non_ascii"))

    for match in _SPLIT_SPACES.finditer(text):
        # `3 500` with a thin or no-break space: a figure split across a
        # separator no formatter emits. One violation, not two small numerals.
        run = re.match(r"\d[\d" + _NO_BREAK_SPACES + r"]*\d", text[match.start():], re.ASCII)
        end = match.start() + (len(run.group(0)) if run else len(match.group(0)))
        found.append(Numeral(text[match.start():end], match.start(), end, "non_ascii"))

    split_spans = [(n.start, n.end) for n in found if n.kind == "non_ascii" and n.end - n.start > 1]

    for match in _TOKEN.finditer(text):
        if any(s <= match.start() < e for s, e in split_spans):
            continue
        if match.group("date"):
            found.append(Numeral(match.group("date"), match.start(), match.end(), "date"))
            continue
        if match.group("ty"):
            year = Decimal(match.group("tyyear"))
            found.append(Numeral(match.group("ty"), match.start(), match.end(), "year", value=year))
            continue
        found.append(_number(text, match))

    return sorted(found, key=lambda n: (n.start, n.end))


def _prefix(text: str, start: int) -> tuple[bool, bool, int, int | None]:
    """What sits in front of a number: `(negative, currency, begin, paren_begin)`.

    `begin` is where the numeral's own text starts, excluding an opening
    parenthesis; `paren_begin` is where that parenthesis is, if there is one, so
    the caller can claim it only when a `)` closes the figure — `(3)` is minus
    three, but `(see 3 below)` is not.

    A hyphen directly after a digit or letter is a separator (`3-5`, `Q3-24`),
    not a minus sign, so a range reads as two numerals rather than a negative.
    """
    window_start = max(0, start - 4)
    window = text[window_start:start]
    m = _PREFIX.search(window)
    opened, sign_before, symbol, sign_after = (m.group(i) for i in (1, 2, 3, 4))

    def at(group: int) -> int:
        return window_start + m.start(group)

    before_sign = "(" if opened else (text[at(2) - 1] if sign_before and at(2) > 0 else "")
    blocked = bool(before_sign) and (before_sign.isalnum() or before_sign in ")]%")
    leading_sign_ok = bool(sign_before) and not blocked
    negative = (leading_sign_ok and sign_before in "-\u2212\u2013") or bool(sign_after)
    begin = start
    for group, present in ((2, leading_sign_ok), (3, bool(symbol)), (4, bool(sign_after))):
        if present:
            begin = at(group)
            break
    return negative, bool(symbol), begin, at(1) if opened else None


def _number(text: str, match: re.Match[str]) -> Numeral:
    start, end = match.start("num"), match.end("num")
    core = match.group("num")
    value = _number_value(core if not core.startswith(".") else "0" + core)
    negative, currency, begin, paren_begin = _prefix(text, start)

    tail = end
    abbreviated = False
    percent = False

    long_suffix = _SUFFIX_LONG.match(text, tail)
    short_suffix = _SUFFIX_SHORT.match(text, tail)
    percent_suffix = _PERCENT.match(text, tail)
    ordinal = _ORDINAL.match(text, tail)

    if percent_suffix:
        percent, tail = True, percent_suffix.end()
    elif long_suffix:
        abbreviated, tail = True, long_suffix.end()
        value *= Decimal(10) ** _SCALE[long_suffix.group(1).lower()]
    elif short_suffix and not ordinal:
        abbreviated, tail = True, short_suffix.end()
        value *= Decimal(10) ** _SCALE[short_suffix.group(0).lower()]
    elif ordinal:
        tail = ordinal.end()

    if paren_begin is not None and text[tail:tail + 1] == ")":
        negative, begin, tail = True, paren_begin, tail + 1

    if negative:
        value = -value

    surface = text[begin:tail]
    plain = "." not in core and "," not in core and not (negative or currency or abbreviated or percent)

    if ordinal and not (abbreviated or percent) and "." not in core:
        return Numeral(surface, begin, tail, "ordinal", value=value)
    if plain and tail == end and value <= MAX_LIST_MARKER:
        following, after = text[end:end + 1], text[end + 1:end + 2]
        if following in {".", ")"} and (after == "" or after.isspace()) and _LIST_LEAD.match(_line_before(text, begin)):
            return Numeral(surface, begin, tail, "structural", value=value)
    if plain and value <= MAX_STEP and _STEP_LEAD.search(text[:begin]):
        return Numeral(surface, begin, tail, "structural", value=value)
    kind = "percent" if percent else "abbreviated" if abbreviated else "money" if currency else "number"
    return Numeral(surface, begin, tail, kind, value=value, percent=percent, abbreviated=abbreviated)
