"""What the engine said, indexed so a figure can be traced to it. [ADR-008]

`FactIndex` flattens the facts and records every spelling a formatter may print for
them. The guard asks it one question — "is this value a fact?" — and the composer
asks it another — "what is at this path?". Split out of `guard`, which
re-exports `FactIndex` and `_flatten`.

Standard library only, plus the formatter and the sibling extractor: vendored.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from application.capabilities import format as fmt
from application.numeric.extract import extract_numerals


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
        """`facts` as an index: pass one through, build one from a dict or a list of dicts."""
        return facts if isinstance(facts, FactIndex) else cls.from_facts(facts)

    def paths(self) -> list[str]:
        """Every dotted path the facts define, sorted."""
        return sorted(self.leaves)

    def nearest(self, value: Decimal) -> Decimal | None:
        """The closest fact value: the thing a changed digit was probably meant to be."""
        if not self.values:
            return None
        return min(self.values, key=lambda v: (abs(v - value), v))
