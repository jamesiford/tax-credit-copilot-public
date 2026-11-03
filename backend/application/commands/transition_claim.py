"""Move a claim cell along its lifecycle. [CH-05]

A **command**. The lifecycle is the domain's (`ProgramClaim.transition_to`), so an
illegal move — a certified cell quietly reverting to assessed — is refused there,
not here. The history is append-only: the earlier state stays readable.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from application.capabilities.errors import ClaimNotFound
from application.identity import Policy
from application.mediator import Command
from domain.claims import ClaimStatus, ProgramClaim, Provenance


class NoClaimToTransition(ClaimNotFound, LookupError):
    """There is no recorded claim for this cell, so there is nothing to move."""


@dataclass(frozen=True)
class TransitionClaimCommand(Command):
    client_id: int = 0
    program_code: str = ""
    tax_year: int = 0
    status: ClaimStatus = ClaimStatus.ASSESSED
    decline_reason: str | None = None
    claimed_usd: Decimal | None = None
    certified_usd: Decimal | None = None
    filing_reference: str | None = None
    provenance: Provenance | None = None
    policy = Policy.WRITER


def next_claim(current: ProgramClaim, command: TransitionClaimCommand) -> ProgramClaim:
    """The claim after the move. Pure, so a preview shows exactly what a commit writes."""
    return current.transition_to(
        command.status,
        decided_by=command.actor,
        decline_reason=command.decline_reason,
        claimed_usd=command.claimed_usd,
        certified_usd=command.certified_usd,
        filing_reference=command.filing_reference,
        provenance=command.provenance,
    )


def current_claim(command: TransitionClaimCommand) -> ProgramClaim:
    from application.wiring import get_claim_repository

    current = get_claim_repository().current(command.client_id, command.program_code, command.tax_year)
    if current is None:
        raise NoClaimToTransition(
            f"No claim recorded for client {command.client_id}, "
            f"{command.program_code.upper()}, TY{command.tax_year}."
        )
    return current


def handle_transition_claim(command: TransitionClaimCommand) -> dict[str, Any]:
    from application.wiring import get_claim_repository

    return get_claim_repository().record(next_claim(current_claim(command), command)).to_dict()
