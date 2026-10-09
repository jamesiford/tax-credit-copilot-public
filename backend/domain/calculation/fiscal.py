"""Fiscal windows and tax-year labels — two things that are not the same thing.

A **fiscal window** is a fact about a client: the begin and end dates of their
accounting year. It comes from `EntityFiscalYearRules` in the source system.

A **tax year** is a label a taxing authority puts on a period, and authorities
disagree about how to assign it. Georgia reg 110-9-1-.02(1)(a) labels a tax year
by the year it **begins**; the common business convention labels a fiscal year by
the year it **ends**. For a calendar-year filer the two agree, which is exactly
why conflating them stayed invisible.

They must not be conflated, because the tax year selects the statute [ADR-005].
Georgia's weekly wage floor was $636 in 2023 and $686 in 2024 — an off-by-one
year is a $50 change in the eligibility bar. And the floor is not monotonic
(2025 is $680, *below* 2024), so the error does not even fail in a consistent
direction. It cannot be reasoned about as conservative.

`domain/calculation/onezero.py:fiscal_year_of` is the older helper. It returns
the *business* label — the year the window ends — and it is fine for that. It is
not a statutory function and nothing that resolves a floor should call it.

Nothing here derives a window from a guess. When neither the client nor the
programme supplies the information, the result says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

TaxYearLabel = Literal["begins", "ends"]

#: Where a window came from, most trustworthy first.
WindowBasis = Literal["client_rules", "assumed_calendar"]


@dataclass(frozen=True)
class FiscalWindow:
    """One client's fiscal year, and the tax year the statute calls it."""

    begin: date
    end: date
    tax_year: int
    label_convention: TaxYearLabel
    basis: WindowBasis
    note: str = ""

    @property
    def assumed(self) -> bool:
        """True when no client fiscal rule was available and a calendar year was assumed."""
        return self.basis != "client_rules"

    @property
    def is_calendar(self) -> bool:
        """A calendar window begins and ends in the same year.

        Worth naming: for these the labelling convention cannot change the
        answer, which is why the conflation has never produced a wrong figure
        here and why it is safe to leave calendar clients alone.
        """
        return self.begin.year == self.end.year

    @property
    def convention_matters(self) -> bool:
        """True when the two labelling conventions would disagree for this window."""
        return not self.is_calendar

    def tax_year_under(self, convention: TaxYearLabel) -> int:
        return self.begin.year if convention == "begins" else self.end.year

    def as_dict(self) -> dict:
        return {
            "begin": self.begin.isoformat(),
            "end": self.end.isoformat(),
            "tax_year": self.tax_year,
            "label_convention": self.label_convention,
            "basis": self.basis,
            "assumed": self.assumed,
            "is_calendar": self.is_calendar,
            "convention_matters": self.convention_matters,
            # What the OTHER reading would have produced. Shown so a reviewer can
            # see the size of the open question rather than take it on trust.
            "tax_year_if_labelled_by_end": self.tax_year_under("ends"),
            "tax_year_if_labelled_by_begin": self.tax_year_under("begins"),
            "note": self.note,
        }


def resolve_tax_year(begin: date, end: date, convention: TaxYearLabel) -> int:
    """The tax year a window belongs to, under a named convention."""
    if end < begin:
        raise ValueError(f"fiscal window ends ({end}) before it begins ({begin})")
    return begin.year if convention == "begins" else end.year


def window_from_client_rules(
    begin: date, end: date, convention: TaxYearLabel, *, note: str = ""
) -> FiscalWindow:
    """A window taken from the client's own fiscal-year rule. No derivation."""
    return FiscalWindow(
        begin=begin,
        end=end,
        tax_year=resolve_tax_year(begin, end, convention),
        label_convention=convention,
        basis="client_rules",
        note=note or "From the client's fiscal-year rule in the source system.",
    )


def assumed_calendar_window(tax_year: int, convention: TaxYearLabel) -> FiscalWindow:
    """A calendar year, used when the client's own rule is unavailable.

    Flagged `assumed` so a caller can surface it. This is the current behaviour
    of every calculating path, and stating it is the point: an assumption that
    announces itself can be corrected, and one that does not cannot.
    """
    return FiscalWindow(
        begin=date(tax_year, 1, 1),
        end=date(tax_year, 12, 31),
        tax_year=tax_year,
        label_convention=convention,
        basis="assumed_calendar",
        note=(
            "No fiscal-year rule on file for this client, so a calendar year is "
            "assumed. Both labelling conventions agree for a calendar year, so "
            "the tax year is unambiguous — but the WINDOW may not match the "
            "client's actual accounting year."
        ),
    )
