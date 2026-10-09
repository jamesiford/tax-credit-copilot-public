"""Seed onboarding assertions, so the coverage matrix has variance to show.

**The claimed figures here are ILLUSTRATIVE. We made them up.** No client or
partner has supplied a prior filing for any of these accounts, so there is
nothing real to record. They exist because the product's central question is
"what were you entitled to, against what you actually claimed", and a matrix
where every cell reads `unclaimed` demonstrates none of it.

Every row is written with `provenance=client_asserted` and
`provenance_verified=False`, so the interface renders them as unverified and
never as computed. **The identified side is real** — it comes from the engine
over real payroll. Only the claimed side is invented, and therefore so is any
recoverable or exposure figure derived from it.

Say that out loud before showing the coverage matrix to anyone. A viewer who
discovers it themselves will reasonably wonder what else was staged.

Run it after assessing, so each cell already has an `identified_usd` to compare
against:

    cd backend
    python -m data.seed_claims
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from application.wiring import get_claim_repository
from domain.claims import ClaimStatus, EngagementScope, ProgramEngagement, Provenance

# (client, program, year, claimed, note) — what each client says they already
# claim. Chosen to exercise every reading the matrix can produce, because a demo
# where every cell says the same thing demonstrates nothing.
#
# The note travels to the screen as `filing_reference`, so it names itself as
# illustrative rather than reading like a fact about the client.
_ASSERTIONS = [
    # Under-claimed: we compute ~$787k against an asserted $410k. The retroactive
    # product in one row.
    (1001, "GA_JTC", 2023, Decimal("410000"), "Illustrative assertion — no prior filing supplied."),

    # Over-claimed: we compute ~$31k against an asserted $95k. This is the
    # exposure the interface must surface rather than quietly drop.
    (2001, "GA_JTC", 2022, Decimal("95000"), "Illustrative assertion — no prior filing supplied."),

    # Claimed about right — the "confirmed" case, where the audit's value is
    # reassurance rather than recovery.
    (2003, "GA_JTC", 2024, Decimal("45535"), "Illustrative assertion — no prior filing supplied."),
]

# What each client says about their mandate. Without this the matrix cannot tell
# "unclaimed — an opportunity" from "unclaimed — not our mandate".
_ENGAGEMENTS = [
    (1001, "GA_JTC", EngagementScope.IN_SCOPE, None),
    (2001, "GA_JTC", EngagementScope.IN_SCOPE, None),
    (2003, "GA_JTC", EngagementScope.IN_SCOPE, None),
    (2004, "GA_JTC", EngagementScope.PROSPECTIVE, "Proposal outstanding."),
]

# A decline, recorded so later runs stop re-proposing it.
_DECLINES = [
    (2004, "GA_JTC", 2021, "Client is disputing the base year with the DOR; revisit after resolution."),
]


def main() -> int:
    repo = get_claim_repository()
    unchanged = written = 0

    for client_id, program, year, claimed, note in _ASSERTIONS:
        current = repo.current(client_id, program, year)
        if current is None:
            print(f"  skip {client_id} {program} TY{year}: not assessed yet")
            continue

        # Re-runnable: the store is append-only, so recording an assertion that
        # is already live would add a second identical decision to the history
        # every time this ran. `azd up` runs it on every deploy. The note is part
        # of the comparison because it reaches the screen — leaving it out meant
        # a corrected wording could never propagate.
        if (
            current.provenance == Provenance.CLIENT_ASSERTED
            and current.claimed_usd == claimed
            and current.status == ClaimStatus.CLAIMED
            and current.filing_reference == note
        ):
            print(f"  {client_id} {program} TY{year}: already asserted, unchanged")
            continue

        # Preserve what the engine computed; only the claim side is asserted.
        from dataclasses import replace
        import uuid
        from datetime import datetime, timezone

        moment = datetime.now(timezone.utc)
        repo.record(replace(
            current,
            claim_id=str(uuid.uuid4()),
            status=ClaimStatus.CLAIMED,
            provenance=Provenance.CLIENT_ASSERTED,
            claimed_usd=claimed,
            filing_reference=note,
            decided_by="seed_claims.py (illustrative)",
            decided_at=moment,
            effective_from=moment,
            effective_to=None,
        ))
        updated = repo.current(client_id, program, year)
        print(
            f"  {client_id} {program} TY{year}: identified ${updated.identified_usd:,.0f} "
            f"vs claimed ${updated.claimed_usd:,.0f} -> {updated.outcome.value}"
        )

    for client_id, program, year, reason in _DECLINES:
        current = repo.current(client_id, program, year)
        if current is None:
            continue
        if current.status == ClaimStatus.DECLINED:
            print(f"  {client_id} {program} TY{year}: already declined")
            continue
        try:
            repo.record(current.transition_to(
                ClaimStatus.DECLINED,
                decided_by="seed_claims.py (illustrative)",
                decline_reason=reason,
            ))
            print(f"  {client_id} {program} TY{year}: declined")
        except Exception as exc:  # a lifecycle rule said no; that is fine here
            print(f"  {client_id} {program} TY{year}: cannot decline ({exc})")

    for client_id, program, scope, note in _ENGAGEMENTS:
        # Re-runnable like the assertions: setting the scope that is already live
        # would append a duplicate row to an append-only history on every deploy.
        live = {e.program_code: e for e in repo.engagements(client_id)}
        existing = live.get(program)
        if existing is not None and existing.scope == scope and existing.note == note:
            print(f"  {client_id} {program}: {scope.value} (unchanged)")
            unchanged += 1
            continue
        repo.set_engagement(ProgramEngagement(
            client_id=client_id, program_code=program, scope=scope, note=note,
        ))
        written += 1
        print(f"  {client_id} {program}: {scope.value}")

    print(f"seed: {written} engagement row(s) written, {unchanged} already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
