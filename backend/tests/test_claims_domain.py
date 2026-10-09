"""The claim domain: variance, lifecycle, provenance.

`test_claim_repository_contract.py` covers storage. This covers meaning, and the
meaning is the product: a retroactive audit exists to say "you left $340,000 on
the table in 2021", and the same machinery must be equally willing to say "you
claimed $40,000 you cannot substantiate".

The asymmetry is the risk. It would be easy — and commercially tempting — to
build something that surfaces recoverable dollars and quietly rounds exposure
away. Several tests here exist specifically to stop that happening by accident.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from domain.claims import (
    MATERIALITY_USD,
    ClaimError,
    ClaimStatus,
    Outcome,
    ProgramClaim,
    Provenance,
)


def _claim(**overrides) -> ProgramClaim:
    base = {
        "client_id": 1001,
        "program_code": "GA_JTC",
        "tax_year": 2023,
        "status": ClaimStatus.ASSESSED,
        "decided_by": "analyst@example.com",
    }
    base.update(overrides)
    return ProgramClaim(**base)


# ------------------------------------------------------------- the variance


def test_nothing_computed_and_nothing_claimed_is_correct(): 
    claim = _claim(identified_usd=0, claimed_usd=0)
    assert claim.outcome is Outcome.CORRECTLY_NOT_CLAIMED
    assert claim.opportunity_usd == Decimal("0")
    assert claim.is_exposure is False


def test_computed_but_not_claimed_is_an_opportunity():
    claim = _claim(identified_usd=Decimal("140000"), claimed_usd=0)
    assert claim.outcome is Outcome.UNCLAIMED
    assert claim.variance_usd == Decimal("140000")
    assert claim.opportunity_usd == Decimal("140000")


def test_claimed_matching_computed_is_confirmed():
    claim = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("140000.00"),
        claimed_usd=Decimal("140000.00"),
    )
    assert claim.outcome is Outcome.CONFIRMED
    assert claim.opportunity_usd == Decimal("0")


def test_claiming_less_than_computed_is_recoverable():
    """The retroactive product in one assertion."""
    claim = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("480000"),
        claimed_usd=Decimal("140000"),
    )
    assert claim.outcome is Outcome.UNDER_CLAIMED
    assert claim.variance_usd == Decimal("340000")
    assert claim.opportunity_usd == Decimal("340000")
    assert claim.is_exposure is False


def test_claiming_more_than_computed_is_exposure():
    """The half a commercial product would be tempted to suppress."""
    claim = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("100000"),
        claimed_usd=Decimal("140000"),
    )
    assert claim.outcome is Outcome.OVER_CLAIMED
    assert claim.is_exposure is True
    assert claim.variance_usd == Decimal("-40000"), "the sign carries the meaning"


def test_variance_is_signed_and_opportunity_is_not():
    """Two figures because they answer two questions.

    `variance_usd` says which way a cell leans. `opportunity_usd` is the only
    one safe to sum into a headline — summing signed variances would let one
    client's exposure cancel another's recoverable dollars and produce a total
    that is arithmetically correct and completely misleading.
    """
    over = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("100000"), claimed_usd=Decimal("140000"),
    )
    under = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("140000"), claimed_usd=Decimal("100000"),
    )

    assert over.variance_usd + under.variance_usd == Decimal("0")
    assert over.opportunity_usd + under.opportunity_usd == Decimal("40000")


def test_a_rounding_difference_is_not_an_exposure():
    """A cent between a filed form and a recomputation is not a finding."""
    claim = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("140000.00"),
        claimed_usd=Decimal("140000.99"),
    )
    assert claim.outcome is Outcome.CONFIRMED
    assert claim.is_exposure is False

    # Just past the threshold, it is.
    material = _claim(
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("140000.00"),
        claimed_usd=Decimal("140001.01"),
    )
    assert material.outcome is Outcome.OVER_CLAIMED


def test_certifying_below_the_claim_is_also_exposure():
    """The authority disagreed with us. That is a finding too."""
    claim = _claim(
        status=ClaimStatus.CERTIFIED,
        identified_usd=Decimal("140000"),
        claimed_usd=Decimal("140000"),
        certified_usd=Decimal("95000"),
    )
    assert claim.outcome is Outcome.CONFIRMED, "we computed what we claimed"
    assert claim.is_exposure is True, "but the state allowed less"


def test_an_unassessed_cell_reads_as_unassessed():
    """Not "correctly not claimed" — we have not looked."""
    claim = _claim(status=ClaimStatus.NOT_ASSESSED, identified_usd=0)
    assert claim.outcome is Outcome.NOT_ASSESSED


# -------------------------------------------------------------- the lifecycle


def test_a_decline_must_carry_a_reason():
    """Durable knowledge. Without it every later run re-proposes the same thing."""
    with pytest.raises(ClaimError, match="decline_reason"):
        _claim(status=ClaimStatus.DECLINED)

    ok = _claim(
        status=ClaimStatus.DECLINED,
        decline_reason="Client takes the R&D credit instead.",
    )
    assert ok.decline_reason


def test_a_blank_reason_does_not_count():
    with pytest.raises(ClaimError, match="decline_reason"):
        _claim(status=ClaimStatus.DECLINED, decline_reason="   ")


def test_a_claim_needs_a_tax_year():
    """Statute is year-scoped [ADR-005]; a claim without a year cannot be checked."""
    with pytest.raises(ClaimError, match="tax_year"):
        ProgramClaim(client_id=1001, program_code="GA_JTC", tax_year=None)


@pytest.mark.parametrize("target", [ClaimStatus.CERTIFIED, ClaimStatus.CLAIMED])
def test_an_assessed_cell_cannot_jump_to_filed(target):
    """Skipping the proposal step would erase somebody's approval."""
    with pytest.raises(ClaimError, match="cannot move"):
        _claim().transition_to(target, decided_by="lead@example.com")


def test_a_certified_cell_cannot_revert_to_assessed():
    """That would erase a filing without leaving a trace."""
    certified = _claim(status=ClaimStatus.CERTIFIED)
    with pytest.raises(ClaimError, match="cannot move"):
        certified.transition_to(ClaimStatus.ASSESSED, decided_by="lead@example.com")


def test_a_declined_cell_can_be_reproposed():
    """Circumstances change, and next year is a fresh conversation."""
    declined = _claim(status=ClaimStatus.DECLINED, decline_reason="Not this year.")
    reproposed = declined.transition_to(ClaimStatus.PROPOSED, decided_by="lead@example.com")
    assert reproposed.status is ClaimStatus.PROPOSED
    assert reproposed.decline_reason is None, "the old reason must not linger"


def test_every_transition_names_a_decider():
    with pytest.raises(ClaimError, match="decided_by"):
        _claim().transition_to(ClaimStatus.PROPOSED, decided_by="")


def test_a_transition_does_not_mutate_its_predecessor():
    """History is append-only, so the original object must be untouched."""
    original = _claim()
    before = original.to_dict()

    nxt = original.transition_to(ClaimStatus.PROPOSED, decided_by="lead@example.com")

    assert original.to_dict() == before
    assert nxt.claim_id != original.claim_id
    assert nxt.effective_to is None


def test_the_full_happy_path_walks_end_to_end():
    claim = _claim(identified_usd=Decimal("140000"))
    claim = claim.transition_to(ClaimStatus.PROPOSED, decided_by="lead@example.com")
    claim = claim.transition_to(
        ClaimStatus.CLAIMED,
        decided_by="filer@example.com",
        claimed_usd=Decimal("140000"),
        filed_on=date(2024, 3, 15),
        filing_reference="IT-CA-2023-0042",
        provenance=Provenance.FILED_BY_US,
    )
    claim = claim.transition_to(
        ClaimStatus.CERTIFIED,
        decided_by="filer@example.com",
        certified_usd=Decimal("140000"),
        provenance=Provenance.AUTHORITY_CONFIRMED,
    )

    assert claim.status is ClaimStatus.CERTIFIED
    assert claim.outcome is Outcome.CONFIRMED
    assert claim.is_exposure is False
    assert claim.provenance.verified is True


# -------------------------------------------------------------- provenance


@pytest.mark.parametrize("provenance,verified", [
    (Provenance.COMPUTED, True),
    (Provenance.FILED_BY_US, True),
    (Provenance.AUTHORITY_CONFIRMED, True),
    (Provenance.CLIENT_ASSERTED, False),
    (Provenance.INHERITED, False),
])
def test_provenance_says_whether_a_figure_is_verified(provenance, verified):
    """An unverified assertion and a certified filing look identical as a dollar
    figure. The grid must be able to tell them apart."""
    assert _claim(provenance=provenance).provenance.verified is verified


def test_the_wire_shape_exposes_verification():
    """So the UI cannot render both tiers alike without deciding to."""
    asserted = _claim(
        provenance=Provenance.CLIENT_ASSERTED,
        status=ClaimStatus.CLAIMED,
        claimed_usd=Decimal("90000"),
    ).to_dict()

    assert asserted["provenance"] == "client_asserted"
    assert asserted["provenance_verified"] is False


def test_money_crosses_the_wire_as_strings():
    """A claim figure must not meet a float on the way to a browser."""
    wire = _claim(identified_usd=Decimal("140000.55")).to_dict()

    assert wire["identified_usd"] == "140000.55"
    assert isinstance(wire["identified_usd"], str)
    assert all(isinstance(wire[k], str) for k in (
        "identified_usd", "claimed_usd", "certified_usd", "variance_usd", "opportunity_usd",
    ))


def test_floats_are_normalised_at_the_boundary():
    """Callers pass what they have; the domain keeps it exact from there."""
    claim = _claim(identified_usd=0.1, claimed_usd="0.2")
    assert isinstance(claim.identified_usd, Decimal)
    assert claim.identified_usd == Decimal("0.1")
    assert claim.claimed_usd == Decimal("0.2")


# --------------------------------------------------------------- proximity


def test_one_job_short_is_visible_even_though_it_is_worth_nothing():
    """The signal a portfolio view exists to surface.

    A client 0.9 jobs short earns $0 — the same $0 as one fifty jobs short.
    Ranking by dollar value buries them, so the jobs gap is what distinguishes
    a prospect from a non-starter.
    """
    claim = _claim(
        identified_usd=0,
        average_headcount=74.1,
        base_average_headcount=73.0,
        threshold_jobs=2.0,
    )
    assert claim.net_new_jobs == 1.1
    assert claim.jobs_to_threshold == 0.9
    assert claim.near_threshold is True
    assert claim.opportunity_usd == Decimal("0"), "worth nothing today"


def test_fifty_jobs_short_is_not_near_the_threshold():
    claim = _claim(
        identified_usd=0,
        average_headcount=73.0,
        base_average_headcount=73.0,
        threshold_jobs=50.0,
    )
    assert claim.jobs_to_threshold == 50.0
    assert claim.near_threshold is False


def test_a_client_over_the_threshold_has_no_gap():
    claim = _claim(
        average_headcount=84.0, base_average_headcount=73.0, threshold_jobs=2.0,
    )
    assert claim.net_new_jobs == 11.0
    assert claim.jobs_to_threshold == 0.0
    assert claim.near_threshold is False, "already qualifying is not 'nearly'"


def test_a_shrinking_client_has_no_net_new():
    """Below the frozen base is zero net-new, never negative."""
    claim = _claim(
        average_headcount=60.0, base_average_headcount=73.0, threshold_jobs=2.0,
    )
    assert claim.net_new_jobs == 0.0
    assert claim.jobs_to_threshold == 2.0


def test_an_unassessed_gap_is_unknown_not_zero():
    """"We do not know" and "you qualify" must not look the same.

    A `0` here would read as "no gap", i.e. qualifying — the opposite of the
    truth for a cell nobody has run.
    """
    claim = _claim()
    assert claim.net_new_jobs is None
    assert claim.jobs_to_threshold is None
    assert claim.near_threshold is False


def test_a_missing_threshold_leaves_the_gap_unknown():
    claim = _claim(average_headcount=74.0, base_average_headcount=73.0)
    assert claim.net_new_jobs == 1.0
    assert claim.jobs_to_threshold is None


def test_the_wire_shape_carries_the_jobs_reasoning():
    wire = _claim(
        average_headcount=74.1, base_average_headcount=73.0, threshold_jobs=2.0,
    ).to_dict()

    assert wire["net_new_jobs"] == 1.1
    assert wire["jobs_to_threshold"] == 0.9
    assert wire["near_threshold"] is True
