"""Pricing one assessed cell: which programme a state maps to, the claim, and a refreshed decision.

Split from `assessment.py` so the sweep and the pricing read separately. The credit itself
is `tools.credit_math.apply_one_zero_state_credit`; nothing here computes a second one.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from domain.claims import ClaimStatus, ProgramClaim, Provenance


def program_of(program_code: str) -> tuple[str | None, str | None]:
    """The rule-pack file and the code of a PROGRAM (a state, or a code, resolves to its default program); either may be None."""
    from tools.pack_lookup import pack_file_for
    from tools.program_registry import program_for_code

    pack_file = pack_file_for(program_code)
    entry = program_for_code(program_code)
    return pack_file, (entry.code if entry else None)


def priced_claim(
    client_id: int, program_code: str, year: int, average: float, prior: float | None, assessed_by: str,
) -> ProgramClaim | None:
    """The `assessed` claim for one program-year, or None when the program is not registered."""
    from tools.program_credit import apply_one_zero_program_credit

    pack_file, code = program_of(program_code)
    if not code:
        return None
    # Two different reasons the prior year can be missing, and only one of
    # them used to be handled. If the year before HAS payroll it is computed
    # and compared against properly. If it genuinely has none, this is
    # the earliest year held, so it is its own base -- which is what
    # `unit_year_master` already records for an inferred base year. The old
    # `0.0` fallback asserted that nobody worked here the year before and
    # made the entire headcount net-new.
    is_base_year = prior is None
    base = average if is_base_year else prior
    credit = apply_one_zero_program_credit(code, average, prior_period_average_headcount=base)
    return ProgramClaim(
        client_id=client_id,
        program_code=code,
        tax_year=year,
        status=ClaimStatus.ASSESSED,
        provenance=Provenance.COMPUTED,
        identified_usd=Decimal(str(credit.get("annual_credit_usd") or 0)),
        # The jobs reasoning, not just the dollar figure. A cell at $0 is
        # either one hire short or fifty, and only these tell them apart.
        average_headcount=round(average, 2),
        base_average_headcount=round(base, 2),
        threshold_jobs=float(credit.get("threshold") or 0),
        is_base_year=is_base_year,
        assumption_set_id=credit.get("assumption_set_id"),
        rule_pack_version=str(pack_file),
        decided_by=assessed_by,
    )


def refreshed(existing: ProgramClaim, claim: ProgramClaim, assessed_by: str) -> ProgramClaim:
    """The cell's current decision, carrying the new evidence.

    A recalculation is new EVIDENCE, not a new decision. Someone already
    proposed, filed or declined this cell; resetting it to `assessed` would
    erase that and re-propose something the client has already answered.
    """
    moment = datetime.now(timezone.utc)
    return replace(
        existing,
        claim_id=str(uuid.uuid4()),
        identified_usd=claim.identified_usd,
        average_headcount=claim.average_headcount,
        base_average_headcount=claim.base_average_headcount,
        threshold_jobs=claim.threshold_jobs,
        is_base_year=claim.is_base_year,
        assumption_set_id=claim.assumption_set_id,
        rule_pack_version=claim.rule_pack_version,
        decided_by=assessed_by,
        decided_at=moment,
        effective_from=moment,
        effective_to=None,
    )


