"""Priority bands — why you would call a client, and in what order.

The ranking is a PRODUCT decision, so it is pinned here rather than left to
whatever `sorted` happened to do. A band that quietly changes places changes who
somebody rings on Monday morning.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.claims import (
    ON_THE_LINE_JOBS,
    ClaimStatus,
    PriorityBand,
    ProgramClaim,
    declining_reading,
)


def _year(tax_year: int, headcount: float, identified: str = "0", **kwargs) -> ProgramClaim:
    """One measured year in a client's history."""
    base = {"base_average_headcount": 40.0, "threshold_jobs": 2.0}
    return _claim(
        claim_id=f"c{tax_year}",
        tax_year=tax_year,
        average_headcount=headcount,
        identified_usd=Decimal(identified),
        **{**base, **kwargs},
    )


def _claim(**kwargs) -> ProgramClaim:
    base = {
        "claim_id": "c1",
        "client_id": 2001,
        "program_code": "GA_JTC",
        "tax_year": 2023,
        "status": ClaimStatus.ASSESSED,
    }
    return ProgramClaim(**{**base, **kwargs})


def test_the_call_order_is_what_inaction_costs():
    """Not a score. Blending dollars and jobs needs coefficients nobody can justify."""
    assert [b.rank for b in (
        PriorityBand.EXPOSED,
        PriorityBand.ON_THE_LINE,
        PriorityBand.DECLINING,
        PriorityBand.UNCLAIMED_AT_SCALE,
        PriorityBand.NOT_ASSESSED,
        PriorityBand.SETTLED,
    )] == [0, 1, 2, 3, 4, 5]


def test_a_falling_client_outranks_one_that_has_simply_not_filed():
    """Money you are about to lose outranks money you have not collected.

    An unclaimed credit is still there next quarter. A workforce shrinking back
    toward its base year is spending the credit down every month nobody calls.
    """
    assert PriorityBand.DECLINING.rank < PriorityBand.UNCLAIMED_AT_SCALE.rank


def test_declining_is_not_exposure():
    """A forecast must not be filed behind the same word as a finding.

    `exposed` means we have looked at a filed return and believe it is wrong.
    Declining means a headcount is falling. Ranking them alike would be
    defensible; NAMING them alike turns a projection into an accusation.
    """
    assert PriorityBand.DECLINING is not PriorityBand.EXPOSED
    assert PriorityBand.EXPOSED.rank < PriorityBand.DECLINING.rank


def test_a_client_one_hire_short_outranks_one_sitting_on_a_fortune():
    """The rule the whole ranking exists for.

    A client one hire away is worth $0 today — the same $0 as one fifty hires
    away — so ranking by dollar value buries exactly the one worth calling. An
    unclaimed credit is recoverable retroactively; a threshold missed at year
    end is not.
    """
    on_the_line = _claim(
        identified_usd=Decimal("0"),
        average_headcount=11.4, base_average_headcount=10.0, threshold_jobs=2.0,
    )
    fortune = _claim(
        identified_usd=Decimal("607110"),
        average_headcount=90.0, base_average_headcount=10.0, threshold_jobs=2.0,
    )
    assert on_the_line.priority_band is PriorityBand.ON_THE_LINE
    assert fortune.priority_band is PriorityBand.UNCLAIMED_AT_SCALE
    assert on_the_line.priority_band.rank < fortune.priority_band.rank


def test_on_the_line_is_both_sides_of_the_cliff():
    """Gaining and losing eligibility are one fact seen from two directions."""
    short = _claim(average_headcount=11.5, base_average_headcount=10.0, threshold_jobs=2.0)
    over = _claim(average_headcount=12.5, base_average_headcount=10.0, threshold_jobs=2.0)

    assert short.jobs_margin == -0.5
    assert over.jobs_margin == 0.5
    assert short.priority_band is over.priority_band is PriorityBand.ON_THE_LINE


def test_the_margin_does_not_clamp_where_the_gap_does():
    """`jobs_to_threshold` reads 0.0 for one job over and for fifty.

    That clamp is why "about to lose eligibility" could not be computed at all.
    """
    barely = _claim(average_headcount=12.5, base_average_headcount=10.0, threshold_jobs=2.0)
    comfortably = _claim(average_headcount=60.0, base_average_headcount=10.0, threshold_jobs=2.0)

    assert barely.jobs_to_threshold == comfortably.jobs_to_threshold == 0.0
    assert barely.jobs_margin == 0.5
    assert comfortably.jobs_margin == 48.0
    assert barely.priority_band is PriorityBand.ON_THE_LINE
    assert comfortably.priority_band is not PriorityBand.ON_THE_LINE


def test_exposure_outranks_proximity():
    """A finding against a filed return is a deadline somebody else controls."""
    claim = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("1000"),
        claimed_usd=Decimal("90000"),
        average_headcount=11.5, base_average_headcount=10.0, threshold_jobs=2.0,
    )
    assert claim.is_exposure
    assert claim.priority_band is PriorityBand.EXPOSED


def test_a_base_year_is_settled_not_an_opportunity():
    """`identified` is zero BY CONSTRUCTION there, so calling it a gap invents one."""
    claim = _claim(is_base_year=True, identified_usd=Decimal("0"))
    assert claim.priority_band is PriorityBand.SETTLED


def test_never_assessed_is_its_own_band_not_a_zero():
    claim = _claim(status=ClaimStatus.NOT_ASSESSED)
    assert claim.priority_band is PriorityBand.NOT_ASSESSED
    assert claim.jobs_margin is None


def test_an_unmeasurable_margin_never_lands_on_the_line():
    """No headcount reasoning means we cannot say. Silence beats a confident band."""
    claim = _claim(identified_usd=Decimal("50000"), average_headcount=None)
    assert claim.jobs_margin is None
    assert claim.priority_band is PriorityBand.UNCLAIMED_AT_SCALE


@pytest.mark.parametrize("margin", [-ON_THE_LINE_JOBS, 0.0, ON_THE_LINE_JOBS])
def test_the_band_is_inclusive_at_one_whole_job(margin):
    """A fraction of a hire is not an action anybody can take, so the edge counts."""
    claim = _claim(
        average_headcount=10.0 + 2.0 + margin,
        base_average_headcount=10.0,
        threshold_jobs=2.0,
    )
    assert claim.priority_band is PriorityBand.ON_THE_LINE


def test_a_claimed_cell_barely_over_the_line_is_still_on_the_line():
    """A deliberate difference from the endpoint this band replaced.

    `portfolio_proximity` skipped any claimed cell — "a position, not a
    prospect" — which is right when the question is "who might file this year".
    The band asks a wider one: why would I ring them. A client who scraped over
    and filed is fragile next year, and that is a call worth making.
    """
    claim = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("50000"),
        claimed_usd=Decimal("50000"),
        average_headcount=12.5, base_average_headcount=10.0, threshold_jobs=2.0,
    )
    assert not claim.is_exposure
    assert claim.priority_band is PriorityBand.ON_THE_LINE


def test_a_client_comfortably_over_is_not_offered_as_a_prospect():
    """Replaces `test_proximity_excludes_clients_already_qualifying`."""
    claim = _claim(
        identified_usd=Decimal("140000"),
        average_headcount=84.0, base_average_headcount=73.0, threshold_jobs=2.0,
    )
    assert claim.priority_band is PriorityBand.UNCLAIMED_AT_SCALE


def test_the_band_travels_on_the_wire():
    wire = _claim(average_headcount=11.5, base_average_headcount=10.0, threshold_jobs=2.0).to_dict()
    assert wire["priority_band"] == "on_the_line"
    assert wire["priority_rank"] == 1
    assert wire["jobs_margin"] == -0.5


# --- the declining reading -------------------------------------------------
#
# Halloway is the live demonstrator: it peaked at 100.75 in TY2022 and has
# fallen every year since, and it bands as `settled` — "Nothing outstanding" —
# on a client shedding forty jobs. The reading below is what corrects that.


def test_a_client_falling_year_on_year_reads_as_declining():
    reading = declining_reading([
        _year(2021, 85.75, "163345"),
        _year(2022, 100.75, "45500"),
        _year(2023, 92.84),
        _year(2024, 70.34),
        _year(2025, 61.42, base_average_headcount=70.34),
    ])
    assert reading is not None
    assert reading["declining"] is True
    assert reading["years_falling"] == 3
    assert reading["peak_tax_year"] == 2022
    assert reading["latest_tax_year"] == 2025
    assert reading["fallen_by"] == 39.33
    # It fell below the base year it is measured against, so the tranches that
    # opened above it are what is being lost.
    assert reading["below_base"] is True
    assert reading["earned_tax_years"] == [2021, 2022]


def test_a_client_that_dipped_and_recovered_is_not_declining():
    """Northwind fell in TY2022 and has climbed since. Calling it is wrong.

    The reading is about where the client is heading NOW, so it compares the
    two most recent measured years. A dip three years back that has since been
    made up is history, not a reason to ring somebody.
    """
    assert declining_reading([
        _year(2021, 58.82, "20000"),
        _year(2022, 50.92),
        _year(2023, 55.10),
        _year(2024, 59.25),
        _year(2025, 71.42),
    ]) is None


def test_a_client_that_never_earned_anything_is_not_losing_it():
    """Shrinking is only a credit problem if there is a credit to shrink out of.

    Without this the band would fire on every client whose headcount happened
    to tick down, most of whom have no tranche running at all.
    """
    assert declining_reading([
        _year(2023, 30.0),
        _year(2024, 25.0),
        _year(2025, 20.0),
    ]) is None


def test_one_measured_year_says_nothing_about_a_trend():
    assert declining_reading([_year(2025, 20.0, "5000")]) is None


def test_a_flat_year_returns_nothing_rather_than_declining_false():
    """An absent trend and a flat one are different, and only one earns a band."""
    assert declining_reading([
        _year(2024, 50.0, "9000"),
        _year(2025, 50.0),
    ]) is None


def test_the_base_year_is_not_a_measured_year():
    """The base is the ruler, not a reading.

    Including it would make the first credit year look like a rise from the
    base and — more damagingly — let a base year be picked as the peak.
    """
    reading = declining_reading([
        _year(2020, 200.0, is_base_year=True),
        _year(2024, 60.0, "9000"),
        _year(2025, 50.0),
    ])
    assert reading is not None
    assert reading["peak_tax_year"] == 2024
