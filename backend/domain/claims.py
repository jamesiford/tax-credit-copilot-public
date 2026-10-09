"""Program coverage and claim outcomes — the domain model. [Group F]

What a client *claims* is not in the partner's source schema and should not be:
`FlexSchema.txt` describes payroll — who worked, where, for how much. A claim is
a commercial and filing outcome, and it arrives from two directions. We generate
it (calculate, propose, file), or the client asserts it at onboarding ("we
already claim GA JTC through someone else"). Both have to be recorded, or a
coverage view can only ever say "$X is available" and never "...and nothing is
being claimed against it."

Two ideas carry most of the weight here.

**The cell is a variance, not a status.** Claimed-versus-unclaimed is too thin
for a retroactive audit. The question is what was claimed against what we
compute they were entitled to, and the SIGN of that difference is the whole
product: under-claimed is recoverable revenue, over-claimed is exposure. A
product that surfaced the upside and quietly dropped the downside would be
indefensible the first time an authority found one, so `variance_usd` is signed
and `Outcome.OVER_CLAIMED` is a first-class result.

**Provenance is not decoration.** A client's unverified assertion and a
state-certified filing must not render alike on the same grid. `Provenance`
carries `verified`, and the API surfaces it, so the interface can keep the two
tiers visibly apart.

Pure: stdlib only, no I/O, no framework. [ADR-002, ADR-003]
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Protocol


class ClaimStatus(str, Enum):
    """Where a client x program x year sits in the claim lifecycle.

        not_assessed -> assessed -> proposed -+-> claimed -> certified
                                              |                 |
                                              +-> declined      +-> amended
    """

    NOT_ASSESSED = "not_assessed"
    ASSESSED = "assessed"
    PROPOSED = "proposed"
    DECLINED = "declined"
    CLAIMED = "claimed"
    CERTIFIED = "certified"
    AMENDED = "amended"

    @property
    def is_claimed(self) -> bool:
        """Has money actually been claimed against this cell?"""
        return self in {ClaimStatus.CLAIMED, ClaimStatus.CERTIFIED, ClaimStatus.AMENDED}


# Which transitions are legal. A lifecycle that permits anything is not a
# lifecycle, and "certified" quietly reverting to "assessed" would erase a
# filing without a trace.
_ALLOWED_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.NOT_ASSESSED: frozenset({ClaimStatus.ASSESSED}),
    ClaimStatus.ASSESSED: frozenset({ClaimStatus.PROPOSED, ClaimStatus.ASSESSED, ClaimStatus.DECLINED}),
    ClaimStatus.PROPOSED: frozenset({ClaimStatus.CLAIMED, ClaimStatus.DECLINED, ClaimStatus.ASSESSED}),
    # A declined cell can be re-proposed: circumstances change, and a later year
    # of the same program is a fresh conversation.
    ClaimStatus.DECLINED: frozenset({ClaimStatus.PROPOSED, ClaimStatus.ASSESSED}),
    ClaimStatus.CLAIMED: frozenset({ClaimStatus.CERTIFIED, ClaimStatus.AMENDED}),
    ClaimStatus.CERTIFIED: frozenset({ClaimStatus.AMENDED}),
    ClaimStatus.AMENDED: frozenset({ClaimStatus.CERTIFIED, ClaimStatus.AMENDED}),
}


class Provenance(str, Enum):
    """How we know. Drives how confidently a cell may render."""

    COMPUTED = "computed"                        # our engine identified it
    FILED_BY_US = "filed_by_us"                  # we prepared and filed it
    CLIENT_ASSERTED = "client_asserted"          # the client told us — UNVERIFIED
    INHERITED = "inherited"                      # from a prior provider — UNVERIFIED
    AUTHORITY_CONFIRMED = "authority_confirmed"  # confirmed by the state or IRS

    @property
    def verified(self) -> bool:
        """False for anything resting only on somebody's word.

        The coverage matrix must keep these visibly apart: an unverified
        assertion and a certified filing look identical as a dollar figure and
        are not remotely the same claim.
        """
        return self in {
            Provenance.COMPUTED,
            Provenance.FILED_BY_US,
            Provenance.AUTHORITY_CONFIRMED,
        }


class Outcome(str, Enum):
    """The reading of one coverage cell — a comparison, not a state."""

    NOT_ASSESSED = "not_assessed"                    # we have not run it
    CORRECTLY_NOT_CLAIMED = "correctly_not_claimed"  # $0 computed, $0 claimed
    UNCLAIMED = "unclaimed"                          # computed > 0, claimed 0
    CONFIRMED = "confirmed"                          # claimed ~= computed
    UNDER_CLAIMED = "under_claimed"                  # computed > claimed — recoverable
    OVER_CLAIMED = "over_claimed"                    # claimed > computed — EXPOSURE
    OUT_OF_SCOPE = "out_of_scope"                    # not our mandate
    #: The earliest year held. Net-new is a year-over-year delta, so in the first
    #: year there is nothing to measure against and `identified` is zero BY
    #: CONSTRUCTION rather than as a finding about the client. Subtracting a
    #: filed amount from it says something about our data coverage, not about
    #: the return, so the cell is not comparable in either direction.
    BASE_YEAR = "base_year"


class EngagementScope(str, Enum):
    """Whether we are engaged to handle this program at all.

    Without it the matrix cannot tell "unclaimed — an opportunity" from
    "unclaimed — not our mandate". Both render as a gap, and one of them is
    noise that erodes trust in the other.
    """

    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    PROSPECTIVE = "prospective"


class PriorityBand(str, Enum):
    """Why you would call this client, in the order you would call them.

    A NAMED reason rather than a score. Blending dollars and jobs into one
    number needs coefficients nobody can justify, and the point of this ranking
    is that somebody can say it out loud to the client — "you are one hire from
    a credit you currently get nothing for" survives being read aloud in a way
    that "priority 0.73" does not.

    Ordering is by what INACTION costs, then by size within the band. That is
    why `UNCLAIMED_AT_SCALE` sits below `ON_THE_LINE` despite being worth more:
    an unclaimed credit is recoverable retroactively, and a threshold missed at
    year end is not.
    """

    EXPOSED = "exposed"
    ON_THE_LINE = "on_the_line"
    DECLINING = "declining"
    UNCLAIMED_AT_SCALE = "unclaimed_at_scale"
    NOT_ASSESSED = "not_assessed"
    SETTLED = "settled"

    @property
    def rank(self) -> int:
        """Descending call order. Lower sorts first."""
        return _BAND_RANK[self]


_BAND_RANK: dict[PriorityBand, int] = {
    PriorityBand.EXPOSED: 0,
    PriorityBand.ON_THE_LINE: 1,
    PriorityBand.DECLINING: 2,
    PriorityBand.UNCLAIMED_AT_SCALE: 3,
    PriorityBand.NOT_ASSESSED: 4,
    PriorityBand.SETTLED: 5,
}

#: Within this many jobs of the statutory minimum, either side, is "on the line".
#: One whole job, because a fraction of a hire is not an action anyone can take.
ON_THE_LINE_JOBS = 1.0


def declining_reading(claims: list["ProgramClaim"]) -> dict[str, Any] | None:
    """Whether a client's headcount is falling back toward its base year.

    A band that no single claim can carry. `priority_band` reads ONE
    client-programme-year, and a trend is a statement about several — so this
    takes the client's whole history and is applied over the cell-level band.

    **Not `EXPOSED`.** Exposure is "claimed more than we can substantiate", a
    finding against a return somebody has already filed. This is a forecast
    about a year nobody has filed yet, and rendering the two alike would turn a
    projection into an accusation.

    Returns `None` when there is nothing to say, rather than a reading with
    `declining=False` in it — an absent trend and a flat one are different, and
    only one of them is worth a band.
    """
    measured = sorted(
        (c for c in claims if c.average_headcount is not None and not c.is_base_year),
        key=lambda c: c.tax_year,
    )
    if len(measured) < 2:
        return None

    latest, prior = measured[-1], measured[-2]
    if float(latest.average_headcount) >= float(prior.average_headcount):
        return None

    # Tranches are live only if the client actually earned credit at the higher
    # level. A client that never qualified is not losing anything by shrinking.
    earned = [c for c in measured if c.identified_usd > 0]
    if not earned:
        return None

    # How long it has been falling, and from where.
    consecutive = 0
    for older, newer in zip(reversed(measured[:-1]), reversed(measured[1:])):
        if float(newer.average_headcount) < float(older.average_headcount):
            consecutive += 1
        else:
            break

    peak = max(measured, key=lambda c: float(c.average_headcount))
    return {
        "declining": True,
        "years_falling": consecutive,
        "peak_tax_year": peak.tax_year,
        "peak_average_headcount": float(peak.average_headcount),
        "latest_tax_year": latest.tax_year,
        "latest_average_headcount": float(latest.average_headcount),
        "fallen_by": round(
            float(peak.average_headcount) - float(latest.average_headcount), 2
        ),
        "below_base": (
            latest.base_average_headcount is not None
            and float(latest.average_headcount) < float(latest.base_average_headcount)
        ),
        "credit_earned_usd": str(sum((c.identified_usd for c in earned), Decimal("0"))),
        "earned_tax_years": [c.tax_year for c in earned],
    }


class ClaimError(ValueError):
    """A claim was rejected for a domain reason, not a storage one."""


# Dollar equality tolerance. Two figures within this are "the same claim" —
# rounding between a filed form and a recomputation is not a variance worth
# putting in front of a client as an exposure.
MATERIALITY_USD = Decimal("1.00")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class ProgramClaim:
    """One cell of the coverage matrix: client x program x tax year.

    Immutable. A status change produces a NEW record with `effective_from` set
    and the prior one closed — never an update in place. The audit question is
    "what did you believe on the day you filed?", and an in-place update cannot
    answer it.
    """

    client_id: int
    program_code: str
    tax_year: int
    status: ClaimStatus = ClaimStatus.NOT_ASSESSED
    provenance: Provenance = Provenance.COMPUTED

    identified_usd: Decimal = Decimal("0")   # what the engine computed as available
    claimed_usd: Decimal = Decimal("0")      # what was actually claimed
    certified_usd: Decimal = Decimal("0")    # what the authority approved

    # The reasoning behind `identified_usd`, not decoration. A credit is a jobs
    # count against a threshold, and a client one job short shows the same $0 as
    # one fifty jobs short. Without these the coverage matrix can say "nothing
    # here" but never "one hire away", which is the most actionable thing in the
    # book.
    average_headcount: float | None = None
    base_average_headcount: float | None = None
    threshold_jobs: float | None = None

    #: The earliest year held for this client, so there is no prior year to
    #: measure net-new against. Recorded rather than inferred later: an audit
    #: asks what we believed when we filed, and re-deriving it from whichever
    #: claims exist today would move it under a historical record's feet.
    is_base_year: bool = False

    entity_id: int | None = None             # some programs are claimed per legal entity

    # Traceability. A six-year audit is six runs under six rulesets, so a figure
    # that cannot name the run and the statute behind it is not defensible.
    identified_run_id: str | None = None
    assumption_set_id: str | None = None
    rule_pack_version: str | None = None

    filed_on: date | None = None
    filing_reference: str | None = None

    decided_by: str | None = None
    decided_at: datetime | None = None
    decline_reason: str | None = None

    claim_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    effective_from: datetime = field(default_factory=_now)
    effective_to: datetime | None = None

    def __post_init__(self) -> None:
        if not self.program_code:
            raise ClaimError("program_code is required")
        if self.tax_year is None:
            raise ClaimError(
                "tax_year is required: statute is year-scoped [ADR-005], so a "
                "claim without a year cannot be checked against any rules"
            )
        # Normalise money once, at the boundary, so comparisons downstream are
        # Decimal-to-Decimal and never float-to-Decimal.
        object.__setattr__(self, "identified_usd", _money(self.identified_usd))
        object.__setattr__(self, "claimed_usd", _money(self.claimed_usd))
        object.__setattr__(self, "certified_usd", _money(self.certified_usd))
        object.__setattr__(self, "program_code", self.program_code.upper())

        if self.status is ClaimStatus.DECLINED and not (self.decline_reason or "").strip():
            # Mandatory by design. "We take the R&D credit instead" is durable
            # knowledge; without it every later run re-proposes the same thing
            # and the consultant looks like they were not listening.
            raise ClaimError(
                f"decline_reason is required when status is declined "
                f"({self.program_code} TY{self.tax_year})"
            )

    # ---------------------------------------------------------------- keys

    @property
    def cell_key(self) -> tuple[int, str, int]:
        """The coverage-matrix grain."""
        return (self.client_id, self.program_code, self.tax_year)

    @property
    def is_current(self) -> bool:
        return self.effective_to is None

    # ------------------------------------------------------------ variance

    @property
    def variance_usd(self) -> Decimal:
        """`identified - claimed`. **Signed, deliberately.**

        Positive is money left on the table; negative is money claimed that we
        cannot substantiate. Taking the absolute value here would erase the
        distinction the whole retroactive product rests on.

        `None` in a base year: `identified` is zero because there is no prior
        year, so the subtraction produces a number about our coverage rather
        than about the return.
        """
        return self.identified_usd - self.claimed_usd

    @property
    def variance_is_computable(self) -> bool:
        """False where `identified` is not a finding about the client."""
        return not self.is_base_year

    @property
    def outcome(self) -> Outcome:
        """How this cell reads. See OPERATIONAL-DATA-MODEL 6A.6."""
        if self.status is ClaimStatus.NOT_ASSESSED:
            return Outcome.NOT_ASSESSED

        # Before any comparison: a base year has nothing to compare against.
        # Classifying it as over-claimed turns "we hold one year of payroll"
        # into a specific, alarming finding about a filed return.
        if self.is_base_year:
            return Outcome.BASE_YEAR

        variance = self.variance_usd

        if not self.status.is_claimed:
            # Nothing claimed. Either there was nothing to claim, or there was.
            if self.identified_usd <= MATERIALITY_USD:
                return Outcome.CORRECTLY_NOT_CLAIMED
            return Outcome.UNCLAIMED

        if abs(variance) <= MATERIALITY_USD:
            return Outcome.CONFIRMED
        if variance > 0:
            return Outcome.UNDER_CLAIMED
        return Outcome.OVER_CLAIMED

    @property
    def is_exposure(self) -> bool:
        """Claimed more than we can substantiate, or certified below what was claimed.

        Both are things we have discovered and cannot un-know.
        """
        if self.is_base_year:
            return False
        if self.outcome is Outcome.OVER_CLAIMED:
            return True
        if self.status is ClaimStatus.CERTIFIED:
            return self.claimed_usd - self.certified_usd > MATERIALITY_USD
        return False

    @property
    def opportunity_usd(self) -> Decimal:
        """Recoverable dollars only — never negative.

        Distinct from `variance_usd` on purpose: this is the figure that may be
        summed into a headline, and summing signed variances would let an
        exposure silently cancel out somebody else's opportunity.
        """
        if self.is_base_year:
            return Decimal("0")
        return max(Decimal("0"), self.variance_usd)

    # --------------------------------------------------------- proximity

    @property
    def net_new_jobs(self) -> float | None:
        """Qualifying jobs above the frozen base, or None if not assessed."""
        if self.average_headcount is None or self.base_average_headcount is None:
            return None
        return round(max(0.0, self.average_headcount - self.base_average_headcount), 2)

    @property
    def jobs_to_threshold(self) -> float | None:
        """How many more qualifying jobs would cross the statutory minimum.

        `0.0` means already over. `None` means we cannot say — and saying "we do
        not know" is the honest answer where a `0` would read as "you qualify".
        """
        net_new = self.net_new_jobs
        if net_new is None or self.threshold_jobs is None:
            return None
        return round(max(0.0, self.threshold_jobs - net_new), 2)

    @property
    def jobs_margin(self) -> float | None:
        """Signed distance from the statutory minimum. Negative is short, positive is over.

        `jobs_to_threshold` clamps at zero, so a client one job over and a
        client fifty over both read `0.0` — which makes "about to lose
        eligibility" uncomputable from it. The threshold is a cliff, and which
        side of it you are on next year is the question this answers.
        """
        net_new = self.net_new_jobs
        if net_new is None or self.threshold_jobs is None:
            return None
        return round(net_new - self.threshold_jobs, 2)

    @property
    def near_threshold(self) -> bool:
        """Short of the minimum, but by less than one whole job.

        The signal a portfolio view exists to surface: a client here earns $0
        today and would earn the full credit for one more qualifying hire.
        Ranking by dollar value buries them, because their dollar value is zero.
        """
        gap = self.jobs_to_threshold
        return gap is not None and 0 < gap <= 1.0

    @property
    def priority_band(self) -> PriorityBand:
        """Why you would call about this cell. See `PriorityBand`.

        Order of the tests is the decision. Exposure outranks proximity because
        a finding against a filed return is a deadline somebody else controls.
        A base year is SETTLED rather than unclaimed: its `identified` is zero
        by construction, so calling it an opportunity would invent one.

        **A BAND IS NEVER DERIVED FROM AN UNVERIFIED CLAIM.** `variance_usd` and
        `opportunity_usd` keep their meanings for the Position view, which
        exists to compare against an assertion and says so on screen. The band
        is different: it is a RANKING, and it puts a word next to a client's
        name. "Exposed" on somebody's unsupported word is an accusation we
        cannot stand behind, and netting a made-up claim off a real identified
        figure turns $31k of found credit into "Nothing outstanding".

        So where the claimed side is unverified, only `identified_usd` — the
        one number we computed — decides.
        """
        if self.is_base_year:
            return PriorityBand.SETTLED
        if self.status is ClaimStatus.NOT_ASSESSED:
            return PriorityBand.NOT_ASSESSED
        if self.is_exposure and self.provenance.verified:
            return PriorityBand.EXPOSED

        margin = self.jobs_margin
        if margin is not None and abs(margin) <= ON_THE_LINE_JOBS:
            return PriorityBand.ON_THE_LINE
        outstanding = (
            self.opportunity_usd if self.provenance.verified else self.identified_usd
        )
        if outstanding > MATERIALITY_USD:
            return PriorityBand.UNCLAIMED_AT_SCALE
        return PriorityBand.SETTLED

    # ----------------------------------------------------------- transition

    def transition_to(
        self,
        status: ClaimStatus,
        *,
        decided_by: str,
        decline_reason: str | None = None,
        claimed_usd: Decimal | float | None = None,
        certified_usd: Decimal | float | None = None,
        filed_on: date | None = None,
        filing_reference: str | None = None,
        provenance: Provenance | None = None,
        at: datetime | None = None,
    ) -> "ProgramClaim":
        """Return the NEXT record in this cell's history.

        Does not mutate; the caller closes the current record and appends this
        one. Raises `ClaimError` on an illegal transition rather than recording
        a history that could not have happened.
        """
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            allowed = ", ".join(sorted(s.value for s in _ALLOWED_TRANSITIONS[self.status]))
            raise ClaimError(
                f"cannot move {self.program_code} TY{self.tax_year} from "
                f"{self.status.value} to {status.value}. Allowed: {allowed or 'none'}."
            )
        if not (decided_by or "").strip():
            raise ClaimError("decided_by is required: every status change is somebody's decision")

        moment = at or _now()
        return replace(
            self,
            claim_id=str(uuid.uuid4()),
            status=status,
            provenance=provenance or self.provenance,
            claimed_usd=_money(claimed_usd) if claimed_usd is not None else self.claimed_usd,
            certified_usd=_money(certified_usd) if certified_usd is not None else self.certified_usd,
            filed_on=filed_on if filed_on is not None else self.filed_on,
            filing_reference=filing_reference if filing_reference is not None else self.filing_reference,
            decline_reason=decline_reason if decline_reason is not None else (
                self.decline_reason if status is ClaimStatus.DECLINED else None
            ),
            decided_by=decided_by,
            decided_at=moment,
            effective_from=moment,
            effective_to=None,
        )

    # ---------------------------------------------------------------- shape

    def to_dict(self) -> dict[str, Any]:
        """Wire shape. Money as strings — a claim figure must not meet a float."""
        return {
            "claim_id": self.claim_id,
            "client_id": self.client_id,
            "entity_id": self.entity_id,
            "program_code": self.program_code,
            "tax_year": self.tax_year,
            "status": self.status.value,
            "provenance": self.provenance.value,
            "provenance_verified": self.provenance.verified,
            "identified_usd": str(self.identified_usd),
            "claimed_usd": str(self.claimed_usd),
            "certified_usd": str(self.certified_usd),
            "variance_usd": None if self.is_base_year else str(self.variance_usd),
            "variance_is_computable": self.variance_is_computable,
            "opportunity_usd": str(self.opportunity_usd),
            "average_headcount": self.average_headcount,
            "base_average_headcount": self.base_average_headcount,
            "threshold_jobs": self.threshold_jobs,
            "is_base_year": self.is_base_year,
            "net_new_jobs": self.net_new_jobs,
            "jobs_to_threshold": self.jobs_to_threshold,
            "jobs_margin": self.jobs_margin,
            "near_threshold": self.near_threshold,
            "priority_band": self.priority_band.value,
            "priority_rank": self.priority_band.rank,
            "outcome": self.outcome.value,
            "is_exposure": self.is_exposure,
            "identified_run_id": self.identified_run_id,
            "assumption_set_id": self.assumption_set_id,
            "rule_pack_version": self.rule_pack_version,
            "filed_on": self.filed_on.isoformat() if self.filed_on else None,
            "filing_reference": self.filing_reference,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decline_reason": self.decline_reason,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
        }


@dataclass(frozen=True)
class ProgramEngagement:
    """Whether we are engaged to handle a program for a client at all."""

    client_id: int
    program_code: str
    scope: EngagementScope = EngagementScope.PROSPECTIVE
    effective_from: datetime = field(default_factory=_now)
    effective_to: datetime | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "program_code", self.program_code.upper())

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "program_code": self.program_code,
            "scope": self.scope.value,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "note": self.note,
        }


class ClaimRepository(Protocol):
    """The port. Named for capability, not for a database. [ADR-002]

    Implementations live in `infrastructure/`. Nothing above this layer may
    import `sqlite3` or a database driver.

    Every read takes `client_id` because tenant is the partition key, not a
    predicate: a query that could omit it is a query that could leak one
    client's figures onto another's screen.
    """

    def current(self, client_id: int, program_code: str, tax_year: int) -> ProgramClaim | None:
        """The live record for one cell, or None if never recorded."""

    def history(self, client_id: int, program_code: str, tax_year: int) -> list[ProgramClaim]:
        """Every record for one cell, oldest first."""

    def coverage(
        self,
        client_id: int,
        *,
        program_codes: Iterable[str] | None = None,
        tax_years: Iterable[int] | None = None,
    ) -> list[ProgramClaim]:
        """Live records for one client, optionally narrowed."""

    def portfolio_coverage(
        self,
        *,
        client_ids: Iterable[int] | None = None,
        tax_years: Iterable[int] | None = None,
    ) -> list[ProgramClaim]:
        """Live records across clients — the portfolio matrix."""

    def record(self, claim: ProgramClaim) -> ProgramClaim:
        """Append a record, closing whatever it supersedes. Returns what was stored."""

    def engagements(self, client_id: int) -> list[ProgramEngagement]:
        """Live engagement scope for one client."""

    def set_engagement(self, engagement: ProgramEngagement) -> ProgramEngagement:
        """Append engagement scope, closing the prior entry for that program."""
