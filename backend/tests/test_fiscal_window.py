"""A fiscal window is a fact; a tax year is a label. These must not be conflated.

Georgia reg 110-9-1-.02(1)(a) labels a tax year by the year it **begins**. The
common business convention labels a fiscal year by the year it **ends**. They
agree only for calendar-year filers, and the tax year selects which year's
statute applies [ADR-005] — so the difference is a $50/week change in Georgia's
eligibility bar between TY2023 and TY2024.

`domain/calculation/onezero.py:fiscal_year_of` returns the business label and is
kept for that. The statutory path is `domain/calculation/fiscal.py`, and these
tests pin the separation.
"""
from __future__ import annotations

from datetime import date

import pytest

from certified import CERTIFIED_PROGRAM_CODE, CERTIFIED_TAX_YEAR, FISCAL_WINDOW
from domain.calculation.fiscal import (
    assumed_calendar_window,
    resolve_tax_year,
    window_from_client_rules,
)
from tools.credit_math import resolve_tax_year_convention


class TestTaxYearLabelling:
    def test_the_two_conventions_disagree_for_a_non_calendar_filer(self):
        """A March year-end filer's year runs Apr 2024 - Mar 2025."""
        begin, end = date(2024, 4, 1), date(2025, 3, 31)
        assert resolve_tax_year(begin, end, "begins") == 2024
        assert resolve_tax_year(begin, end, "ends") == 2025

    def test_the_two_conventions_agree_for_a_calendar_filer(self):
        """Why the conflation stayed invisible, and why calendar clients are safe."""
        begin, end = date(2024, 1, 1), date(2024, 12, 31)
        assert resolve_tax_year(begin, end, "begins") == 2024
        assert resolve_tax_year(begin, end, "ends") == 2024

    def test_a_window_reports_whether_the_convention_could_change_its_answer(self):
        calendar = window_from_client_rules(date(2024, 1, 1), date(2024, 12, 31), "begins")
        assert calendar.is_calendar
        assert not calendar.convention_matters

        march = window_from_client_rules(date(2024, 4, 1), date(2025, 3, 31), "begins")
        assert not march.is_calendar
        assert march.convention_matters

    def test_a_window_carries_both_readings_so_the_gap_is_visible(self):
        """A reviewer should see the size of the open question, not take it on trust."""
        payload = window_from_client_rules(
            date(2024, 4, 1), date(2025, 3, 31), "begins"
        ).as_dict()
        assert payload["tax_year_if_labelled_by_begin"] == 2024
        assert payload["tax_year_if_labelled_by_end"] == 2025

    def test_a_backwards_window_is_refused(self):
        with pytest.raises(ValueError, match="ends .* before it begins"):
            resolve_tax_year(date(2025, 3, 31), date(2024, 4, 1), "begins")


class TestProvenance:
    def test_a_client_sourced_window_is_not_an_assumption(self):
        window = window_from_client_rules(date(2023, 7, 28), date(2024, 8, 2), "begins")
        assert window.basis == "client_rules"
        assert window.assumed is False

    def test_an_assumed_window_says_so(self):
        """An assumption that announces itself can be corrected."""
        window = assumed_calendar_window(2024, "begins")
        assert window.assumed is True
        assert window.basis == "assumed_calendar"
        assert "assumed" in window.note.lower()

    def test_an_assumed_calendar_year_is_still_unambiguous_about_its_tax_year(self):
        """The window may be wrong; the LABEL cannot be, because both readings agree."""
        for convention in ("begins", "ends"):
            assert assumed_calendar_window(2024, convention).tax_year == 2024


class TestGeorgiaConvention:
    def test_georgia_labels_a_tax_year_by_the_year_it_begins(self):
        convention = resolve_tax_year_convention("GA_JTC", 2023)
        assert convention["label"] == "begins"
        assert convention["regulation"] == "110-9-1-.02(1)(a)"
        assert convention["assumed"] is False

    def test_georgia_is_read_from_the_regulation_and_not_yet_confirmed(self):
        """Authored honestly: we read it, the partner has not confirmed it. PILOT-07."""
        assert resolve_tax_year_convention("GA_JTC", 2023)["unconfirmed"] is True

    def test_every_authored_georgia_year_carries_the_convention(self):
        from tools.credit_math import authored_years

        for year in authored_years("ga_jtc.json"):
            assert resolve_tax_year_convention("GA_JTC", year)["assumed"] is False, (
                f"TY{year} lost its tax-year convention"
            )

    def test_a_programme_without_an_authored_convention_flags_the_default(self):
        convention = resolve_tax_year_convention("SC_JTC")
        assert convention["label"] == "begins"
        assert convention["assumed"] is True
        assert convention["unconfirmed"] is True


def test_the_certified_window_resolves_to_the_certified_tax_year():
    """The whole point, in one assertion.

    The reference window opens 28 July 2023 and closes 2 August 2024, and the
    certified run prices it at TY2023 — $636, not TY2024's $686. Under
    `begins` the new resolver agrees. Under `ends` it would not, which is
    precisely the wrong answer this separation exists to prevent.
    """
    begin, end = FISCAL_WINDOW
    convention = resolve_tax_year_convention(CERTIFIED_PROGRAM_CODE, CERTIFIED_TAX_YEAR)

    window = window_from_client_rules(begin, end, convention["label"])

    assert window.tax_year == CERTIFIED_TAX_YEAR
    assert window.convention_matters, "a 53-week window is not a calendar year"
    assert window.tax_year_under("ends") == CERTIFIED_TAX_YEAR + 1
