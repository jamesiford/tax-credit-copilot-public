"""Record a claim the platform did not compute. [CH-05]

Onboarding assertions and inherited records. A **command**: it changes what the
business believes about a cell, so it goes through the mediator, carries an
author, and is refused unless that author is entitled to write.

Moved out of the claims router, which used to build the claim and call the
repository itself: the one write path that skipped the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from application.identity import Policy
from application.mediator import Command
from domain.claims import ClaimStatus, ProgramClaim, Provenance


def statutory_threshold(program_code: str) -> float | None:
    """The programme's minimum-new-jobs figure, or None if we hold no pack."""
    from tools.credit_math import PROGRAM_CODE_TO_PACK, _load_pack

    pack_file = PROGRAM_CODE_TO_PACK.get(program_code.upper())
    if not pack_file:
        return None
    try:
        pack = _load_pack(pack_file)
    except FileNotFoundError:
        return None
    value = (pack.get("thresholds") or {}).get("minimum_new_jobs")
    return float(value) if value is not None else None


@dataclass(frozen=True)
class RecordClaimCommand(Command):
    client_id: int = 0
    program_code: str = ""
    tax_year: int = 0
    status: ClaimStatus = ClaimStatus.ASSESSED
    provenance: Provenance = Provenance.CLIENT_ASSERTED
    identified_usd: Decimal = Decimal("0")
    claimed_usd: Decimal = Decimal("0")
    certified_usd: Decimal = Decimal("0")
    average_headcount: float | None = None
    base_average_headcount: float | None = None
    threshold_jobs: float | None = None
    entity_id: int | None = None
    filing_reference: str | None = None
    decline_reason: str | None = None
    identified_run_id: str | None = None
    assumption_set_id: str | None = None
    rule_pack_version: str | None = None
    policy = Policy.WRITER


def build_claim(command: RecordClaimCommand) -> ProgramClaim:
    """The claim this command would record. Pure, so a preview can show it unwritten.

    A caller who supplies headcounts but no threshold gets the programme's
    statutory minimum, so the recorded gap is a real one.
    """
    threshold = command.threshold_jobs
    if threshold is None and command.average_headcount is not None:
        threshold = statutory_threshold(command.program_code)
    return ProgramClaim(
        client_id=command.client_id,
        program_code=command.program_code,
        tax_year=command.tax_year,
        status=command.status,
        provenance=command.provenance,
        identified_usd=command.identified_usd,
        claimed_usd=command.claimed_usd,
        certified_usd=command.certified_usd,
        average_headcount=command.average_headcount,
        base_average_headcount=command.base_average_headcount,
        threshold_jobs=threshold,
        entity_id=command.entity_id,
        filing_reference=command.filing_reference,
        decline_reason=command.decline_reason,
        identified_run_id=command.identified_run_id,
        assumption_set_id=command.assumption_set_id,
        rule_pack_version=command.rule_pack_version,
        decided_by=command.actor,
    )


def handle_record_claim(command: RecordClaimCommand) -> dict[str, Any]:
    from application.wiring import get_claim_repository

    return get_claim_repository().record(build_claim(command)).to_dict()
