"""The numeric integrity guard [ADR-008].

A figure on a tax return is either the engine's figure or it is wrong, and a
language model can misstate a number it was handed as easily as it can invent
one. So nothing a model writes reaches a reader unless every numeral in it can be
traced to a value the engine produced. This module is that check.

**Zero tolerance.** A numeral passes only if it *equals* a fact (exact `Decimal`
equality — no rounding allowance, no "close enough"), or it appeared in the
reader's own question or the resolved scope, or it is structural (a list marker,
a step number, a small ordinal). An abbreviation (`$3.5K`, `1.2 million`) passes
only if the formatter would have printed exactly that spelling. A rejected
sentence is an inconvenience; a wrong figure on a tax return is not.

**What counts as a numeral.** Plain and grouped numbers, decimals (with or
without a leading digit), negatives (`-3`, `(3)`), money, percentages,
abbreviations, ranges (each end is its own numeral), numbers next to units
(`12.67 FTE`), ISO dates and `TY2023`-style tokens. Number *words* ("twelve") are
not numerals here — the narrator's prompt forbids them for figures, and a guard
that guessed at English would be wrong in both directions. Digits that are not
ASCII (full-width, Arabic-Indic, vulgar fractions) are rejected outright rather
than normalised: no formatter emits them, so their only use is evasion.

**Standard library only**, plus `application.capabilities.format`, which is itself
standard-library only. Both are vendored into the orchestrator container.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from application.capabilities import format as fmt

PASS = "pass"
REJECTED = "rejected"

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


@dataclass(frozen=True)
class Numeral:
    """One figure found in a piece of text."""

    text: str
    start: int
    end: int
    kind: str  # number | money | percent | abbreviated | ordinal | year | date | structural | non_ascii
    value: Decimal | None = None
    percent: bool = False
    abbreviated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "start": self.start, "end": self.end, "kind": self.kind,
            "value": None if self.value is None else format(self.value, "f"),
        }


@dataclass(frozen=True)
class Violation:
    """A numeral the guard refused, and why."""

    numeral: Numeral
    reason: str
    stage: str = "final"
    nearest: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "numeral": self.numeral.to_dict(), "reason": self.reason, "stage": self.stage,
            "nearest_fact": None if self.nearest is None else format(self.nearest, "f"),
        }


@dataclass(frozen=True)
class GuardResult:
    status: str
    violations: tuple[Violation, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == PASS

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "violations": [v.to_dict() for v in self.violations]}


@dataclass(frozen=True)
class AllowedContext:
    """Numerals the reader supplied: their question, the resolved scope.

    "5 hires" in the question may be said back; a tax year the page is scoped to
    may be named. Nothing here is a figure the engine produced, so it is the
    narrowest door in the module — the caller passes it explicitly and it is
    never inferred from the narration.
    """

    values: frozenset[Decimal] = frozenset()
    percents: frozenset[Decimal] = frozenset()
    surfaces: frozenset[str] = frozenset()
    years: frozenset[int] = frozenset()

    @classmethod
    def build(
        cls,
        *texts: str,
        years: Iterable[int] = (),
        numbers: Iterable[Any] = (),
    ) -> "AllowedContext":
        """From the reader's own words, plus explicit scope (tax year, client id)."""
        values: set[Decimal] = {Decimal(int(y)) for y in years}
        values.update(fmt.to_decimal(n) for n in numbers)
        percents: set[Decimal] = set()
        surfaces: set[str] = set()
        for text in texts:
            for numeral in extract_numerals(text or ""):
                if numeral.kind in {"structural", "non_ascii"}:
                    continue
                if numeral.kind == "date":
                    surfaces.add(numeral.text)
                elif numeral.value is not None:
                    (percents if numeral.percent else values).add(numeral.value)
                    if numeral.abbreviated:
                        surfaces.add(numeral.text)
        return cls(
            values=frozenset(values), percents=frozenset(percents),
            surfaces=frozenset(surfaces), years=frozenset(int(y) for y in years),
        )


# ----------------------------------------------------------------- extraction


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


# ------------------------------------------------------------------- the index


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), item, out)
    elif isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            _flatten(f"{prefix}.{position}" if prefix else str(position), item, out)
    else:
        out[prefix] = value


@dataclass(frozen=True)
class FactIndex:
    """What the engine said, flattened, with every spelling a formatter may print.

    `leaves` maps a dotted path to its value; `values` is every canonical number
    the facts supply (numbers, numeric strings, and the digits inside any string
    — a citation, a date, a note the engine wrote); `spellings` is every
    rendering a numeric formatter can emit for them; `percent_values` are the
    scaled values of facts known to be ratios or percentages.
    """

    leaves: Mapping[str, Any] = field(default_factory=dict)
    values: frozenset[Decimal] = frozenset()
    spellings: frozenset[str] = frozenset()
    percent_values: frozenset[Decimal] = frozenset()
    dates: frozenset[str] = frozenset()
    ambiguous: frozenset[str] = frozenset()
    percent_paths: frozenset[str] = frozenset()

    @classmethod
    def from_facts(
        cls,
        facts_list: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        names: Sequence[str] | None = None,
        percent_paths: Iterable[str] = (),
    ) -> "FactIndex":
        """Index one facts dict, or several.

        With several, pass `names` to prefix each (`credit.annual_credit_usd`
        becomes `client_eligibility.credit.annual_credit_usd`); without names a
        path that two results define differently is *ambiguous* and cannot be
        used by a placeholder.
        """
        if isinstance(facts_list, Mapping):
            facts_list = [facts_list]
        leaves: dict[str, Any] = {}
        ambiguous: set[str] = set()
        for position, facts in enumerate(facts_list):
            flat: dict[str, Any] = {}
            _flatten(names[position] if names else "", facts, flat)
            for path, value in flat.items():
                if path in leaves and leaves[path] != value:
                    ambiguous.add(path)
                leaves.setdefault(path, value)
        return cls._build(leaves, frozenset(ambiguous), frozenset(percent_paths))

    @classmethod
    def _build(cls, leaves: Mapping[str, Any], ambiguous: frozenset[str], percent_paths: frozenset[str]) -> "FactIndex":
        values: set[Decimal] = set()
        spellings: set[str] = set()
        percents: set[Decimal] = set()
        dates: set[str] = set()
        for path, value in leaves.items():
            hinted = path in percent_paths or fmt.infer_formatter(path, value) == "percent_points"
            if isinstance(value, str):
                for numeral in extract_numerals(value):
                    if numeral.kind == "date":
                        dates.add(numeral.text)
                        try:
                            dates.update(fmt.render_variants(numeral.text, "date"))
                        except ValueError:
                            pass
                    elif numeral.value is not None and numeral.kind not in {"structural", "non_ascii"}:
                        values.add(numeral.value)
                        spellings.add(numeral.text)
            if isinstance(value, bool) or value is None:
                continue
            try:
                number = fmt.to_decimal(value)
            except ValueError:
                if isinstance(value, str) or hasattr(value, "isoformat"):
                    try:
                        dates.update(fmt.render_variants(value, "date"))
                    except ValueError:
                        pass
                continue
            values.add(number)
            spellings.update(fmt.numeric_variants(number))
            if hinted:
                percents.add(number)
                percents.add(number.scaleb(2))
                spellings.update(fmt.numeric_variants(number, percent_hint=True))
        return cls(
            leaves=dict(leaves), values=frozenset(values), spellings=frozenset(spellings),
            percent_values=frozenset(percents), dates=frozenset(dates),
            ambiguous=ambiguous, percent_paths=percent_paths,
        )

    def with_percent(self, path: str) -> "FactIndex":
        """The same index, told that `path` is a percentage or a ratio.

        A headcount of 0.125 is not 12.5%. Without being told, the guard cannot
        tell the two apart, so percent spellings are accepted only for facts a
        placeholder has said are percentages (`{{facts.x|percent}}`).
        """
        if path in self.percent_paths:
            return self
        return self._build(self.leaves, self.ambiguous, self.percent_paths | {path})

    @classmethod
    def coerce(cls, facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]") -> "FactIndex":
        return facts if isinstance(facts, FactIndex) else cls.from_facts(facts)

    def paths(self) -> list[str]:
        return sorted(self.leaves)

    def nearest(self, value: Decimal) -> Decimal | None:
        """The closest fact value: the thing a changed digit was probably meant to be."""
        if not self.values:
            return None
        return min(self.values, key=lambda v: (abs(v - value), v))


# ------------------------------------------------------------------- the check


def _judge(numeral: Numeral, facts: FactIndex, context: AllowedContext) -> str | None:
    """Why this numeral is not acceptable, or None if it is."""
    kind, value = numeral.kind, numeral.value
    if kind == "structural":
        return None
    if kind == "non_ascii":
        return "a digit or numeric character that no formatter emits (non-ASCII, or split by a space)"
    if kind == "date":
        if numeral.text in facts.dates or numeral.text in context.surfaces:
            return None
        return "a date that is not in the facts"
    if value is None:
        return "a numeral with no value"
    if kind == "ordinal" and 1 <= value <= MAX_ORDINAL:
        return None
    if numeral.abbreviated:
        if numeral.text in facts.spellings or numeral.text in context.surfaces:
            return None
        return "an abbreviation the formatter did not emit"
    if numeral.percent:
        if value in facts.percent_values or value in context.percents:
            return None
        return "a percentage that is not in the facts"
    if value in facts.values or value in context.values:
        return None
    if kind == "year" and int(value) in context.years:
        return None
    return "a figure that is not in the facts"


def check(
    text: str,
    *,
    facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]",
    allowed_context: AllowedContext | None = None,
    stage: str = "final",
) -> GuardResult:
    """Every numeral in `text` must be a fact, supplied context, or structural.

    Returns `rejected` with each offending numeral and the nearest fact value
    (what a changed digit was probably meant to be). It never softens, rounds or
    rewrites: the caller decides what to show instead.
    """
    index = FactIndex.coerce(facts)
    context = allowed_context or AllowedContext()
    violations = []
    for numeral in extract_numerals(text):
        reason = _judge(numeral, index, context)
        if reason is not None:
            nearest = index.nearest(numeral.value) if numeral.value is not None else None
            violations.append(Violation(numeral, reason, stage=stage, nearest=nearest))
    return GuardResult(REJECTED if violations else PASS, tuple(violations))


def check_raw(text: str, *, allowed_context: AllowedContext | None = None) -> GuardResult:
    """The strict gate on a model's own words: no digit unless the reader supplied it.

    Run before placeholders are substituted. A figure belongs in a placeholder; a
    numeral a model typed — even one that happens to equal a fact — is the model
    producing a number, which is exactly what the architecture forbids. Only the
    reader's own numerals and structural digits pass.
    """
    return check(text, facts=FactIndex(), allowed_context=allowed_context, stage="narration")
