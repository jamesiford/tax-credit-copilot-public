"""A base year has nothing to compare a filed amount against.

Net-new is a year-over-year delta. In the earliest year held there is no prior
year, so `identified` is zero BY CONSTRUCTION rather than as a finding about the
client. Subtracting a filed amount from it produces a number about our data
coverage, not about the return -- which is how Candle Bottle came to open the
portfolio as a $410,000 over-claim exposure against a figure the seed file
itself labels illustrative.

The rule is "is this the earliest year we hold", never a client. A client with
ten years has exactly one base year; a client with one year is all base year.
"""
from __future__ import annotations

from decimal import Decimal

from domain.claims import ClaimStatus, Outcome, ProgramClaim, Provenance


def _claim(**overrides) -> ProgramClaim:
    base = {
        "client_id": 4242,
        "program_code": "GA_JTC",
        "tax_year": 2023,
        "status": ClaimStatus.CLAIMED,
        "provenance": Provenance.CLIENT_ASSERTED,
        "identified_usd": Decimal("0"),
        "claimed_usd": Decimal("410000"),
        "average_headcount": 226.76,
        "base_average_headcount": 226.76,
        "threshold_jobs": 2.0,
        "is_base_year": True,
    }
    base.update(overrides)
    return ProgramClaim(**base)


# --- the base year is not a comparison -------------------------------------


def test_a_base_year_is_not_an_over_claim():
    claim = _claim()

    assert claim.outcome is Outcome.BASE_YEAR
    assert claim.outcome is not Outcome.OVER_CLAIMED


def test_a_base_year_is_not_an_exposure():
    """The alarming half. `identified` being zero says nothing about the return."""
    assert _claim().is_exposure is False


def test_a_base_year_reports_no_computable_variance():
    claim = _claim()

    assert claim.variance_is_computable is False
    assert claim.to_dict()["variance_usd"] is None, (
        "a signed variance here is a number about our coverage, not the return"
    )


def test_a_base_year_contributes_nothing_to_opportunity():
    """It must not be summed into a headline in either direction."""
    assert _claim(claimed_usd=Decimal("0"), identified_usd=Decimal("0")).opportunity_usd == Decimal("0")


def test_a_base_year_under_a_filed_amount_is_still_not_under_claimed():
    """The other direction of the same mistake."""
    claim = _claim(identified_usd=Decimal("500000"), claimed_usd=Decimal("1"))

    assert claim.outcome is Outcome.BASE_YEAR


def test_a_base_year_keeps_everything_except_the_classification():
    cell = _claim().to_dict()

    assert cell["average_headcount"] == 226.76
    assert cell["base_average_headcount"] == 226.76
    assert cell["claimed_usd"] == "410000"
    assert cell["is_base_year"] is True


# --- and only the base year ------------------------------------------------


def test_a_real_over_claim_still_reads_as_an_exposure():
    """Cascade TY2022: $31,185 identified against $95,000 filed, measured
    against a real prior year. If this stops being an exposure the change is
    too broad."""
    claim = _claim(
        tax_year=2022,
        identified_usd=Decimal("31185"),
        claimed_usd=Decimal("95000"),
        average_headcount=117.08,
        base_average_headcount=106.17,
        is_base_year=False,
    )

    assert claim.outcome is Outcome.OVER_CLAIMED
    assert claim.is_exposure is True
    assert claim.variance_usd == Decimal("-63815")
    assert claim.to_dict()["variance_usd"] == "-63815"


def test_a_matching_claim_in_a_later_year_still_confirms():
    claim = _claim(
        tax_year=2024,
        identified_usd=Decimal("45535"),
        claimed_usd=Decimal("45535"),
        is_base_year=False,
    )

    assert claim.outcome is Outcome.CONFIRMED
    assert claim.is_exposure is False


def test_a_flat_year_is_not_a_base_year_even_though_its_base_equals_its_average():
    """`base == average` happens whenever headcount did not move, so it cannot
    be used to detect a base year. Only the recorded fact can."""
    claim = _claim(
        tax_year=2024,
        identified_usd=Decimal("0"),
        claimed_usd=Decimal("95000"),
        average_headcount=60.0,
        base_average_headcount=60.0,
        is_base_year=False,
    )

    assert claim.outcome is Outcome.OVER_CLAIMED, (
        "a flat later year IS comparable; its zero is a finding about the client"
    )
    assert claim.is_exposure is True
