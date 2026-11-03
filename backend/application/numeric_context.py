"""The numerals a reader supplied themselves. [ADR-008]

"5 hires" in the question may be said back; a tax year the page is scoped to may be
named. Nothing here is a figure the engine produced, so it is the narrowest door in
the guard — the caller passes it explicitly and it is never inferred from the
narration. Split out of `numeric_guard`, which re-exports it.

Standard library only, plus the formatter and the sibling extractor: vendored.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from application.capabilities import format as fmt
from application.numeric_extract import extract_numerals


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
