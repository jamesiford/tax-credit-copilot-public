"""The reader's words settle the arguments a model must not choose. [CH-08]

A model NAMES a tool and proposes arguments; the year, the method and a what-if's numbers are the
reader's. A year the model proposes is used only when the reader said it (or it is the conversation's
current year); a what-if number the model chose is dropped; the method is the reader's, and an unnamed
method for a tool that asks for it means every certified method, because the statute has not chosen.
A hallucinated year cannot select a return.

Which arguments a tool holds that are the reader's, and of what kind, is the catalog's to say
(`CapabilitySpec.reader_owned`); nothing here names an argument. Pure functions of the reader's words and
the conversation's year: no gateway, no model, no framework.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.toolset import Clarification, numbers_in, years_in
from application.capabilities import catalog
from application.capabilities.catalog_types import OWNED_EXPLICIT_YEAR, OWNED_METHOD_BOTH, OWNED_SCENARIO, OWNED_SIZE, OWNED_YEAR

_PAY_PERIOD = re.compile(r"pay[\s-]?period", re.IGNORECASE)
_MIN_MAX = re.compile(r"min[\s-]?max", re.IGNORECASE)


@dataclass(frozen=True)
class ReaderWords:
    """What the reader said this turn, and the year the conversation is on."""

    question: str
    conversation_year: int | None = None

    def year(self, proposed: Any, *, allow_state: bool = True) -> int | None:
        said = years_in(self.question)
        state_year = self.conversation_year if allow_state else None
        if isinstance(proposed, int) and not isinstance(proposed, bool) and (proposed in said or proposed == state_year):
            return proposed
        return said[0] if len(said) == 1 else state_year

    def method(self, kind: str, proposed: Any) -> str | None:
        if kind != OWNED_METHOD_BOTH:
            return proposed if isinstance(proposed, str) else None
        pay, minmax = bool(_PAY_PERIOD.search(self.question)), bool(_MIN_MAX.search(self.question))
        return "pay_period" if pay and not minmax else "min_max" if minmax and not pay else "both"

    def years(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> Clarification | None:
        """Settle every year argument; the question to put to the reader when a needed one is missing."""
        for owned in spec.owned(OWNED_YEAR, OWNED_EXPLICIT_YEAR):
            year = self.year(args.get(owned.name), allow_state=owned.kind != OWNED_EXPLICIT_YEAR)
            if year is not None:
                args[owned.name] = year
            elif owned.name in spec.schema.get("required", []) or spec.needs_year:
                return Clarification("year", "no tax year was named")
            else:
                args.pop(owned.name, None)
        return None

    def scenario(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> Clarification | None:
        """A what-if's numbers are the reader's: one the model chose is dropped, and a missing size is asked for."""
        said = numbers_in(self.question)
        for key in catalog.owned_names(OWNED_SIZE, OWNED_SCENARIO):
            if key in args and not (isinstance(args[key], (int, float)) and float(args[key]) in said):
                del args[key]
        if any(o.name not in args for o in spec.owned(OWNED_SIZE)):
            return Clarification("detail", "How many, or by how much?")
        return None

    def tax_years(self, key: str, args: dict[str, Any]) -> None:
        """A data tool's years are the reader's: a year the model named that the reader did not say (and the
        conversation is not on) is replaced by the years they did say, or dropped, which means every year the
        data holds."""
        proposed, said = args.pop(key, None), years_in(self.question)
        allowed = {*said, *([self.conversation_year] if self.conversation_year else [])}
        if isinstance(proposed, dict) and all(isinstance(proposed.get(k), int) and proposed[k] in allowed for k in ("from", "to")):
            args[key] = proposed
            return
        kept = [y for y in proposed if isinstance(y, int) and y in allowed] if isinstance(proposed, list) else []
        if kept or said:
            args[key] = kept or said
