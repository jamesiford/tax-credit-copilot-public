"""How a portfolio of claims reads: totals, and what a cell means in context.

These are business rules, not presentation. Whether a gap counts as an
opportunity depends on the engagement we hold, and that judgement must be
identical whether it reaches a screen, a report, or an export.

**Opportunity and exposure are summed separately, at every level.** They are not
two ends of one number. Netting them would let a client we have over-claimed for
cancel out one we have under-claimed for, and produce a portfolio headline that
is true of nobody — while hiding the exposure, which is the half with a
deadline attached.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.claims import EngagementScope, Outcome, ProgramClaim


def totals(claims: list[ProgramClaim]) -> dict[str, Any]:
    """Money and counts over a set of cells.

    Amounts are serialised as strings. They originate as `Decimal`, and JSON
    numbers are IEEE 754 doubles — round-tripping a cent-accurate figure through
    a float is how money silently loses its last digit.
    """
    opportunity = sum((c.opportunity_usd for c in claims), Decimal("0"))
    exposure = sum(
        (-c.variance_usd for c in claims if c.outcome is Outcome.OVER_CLAIMED),
        Decimal("0"),
    )
    return {
        "identified_usd": str(sum((c.identified_usd for c in claims), Decimal("0"))),
        "claimed_usd": str(sum((c.claimed_usd for c in claims), Decimal("0"))),
        "opportunity_usd": str(opportunity),
        "exposure_usd": str(exposure),
        "cells": len(claims),
        "exposure_cells": sum(1 for c in claims if c.is_exposure),
        "unverified_cells": sum(1 for c in claims if not c.provenance.verified),
    }


def totals_by_program(claims: list[ProgramClaim]) -> dict[str, dict[str, Any]]:
    """One total per programme — the account grid's row totals.

    Summed HERE, as `Decimal`, for the same reason the whole-grid total is: the
    grid used to reduce `opportunity_usd` across cells in the browser, which
    turns a cent-accurate figure into a float the moment it is added. Every
    other dollar on that screen arrives exact and one row of them did not.
    """
    grouped: dict[str, list[ProgramClaim]] = {}
    for claim in claims:
        grouped.setdefault(claim.program_code, []).append(claim)
    return {code: totals(rows) for code, rows in sorted(grouped.items())}


def matrix(
    claims: list[ProgramClaim], engagements: dict[str, EngagementScope]
) -> list[dict[str, Any]]:
    """Cells, each carrying its own reading rather than a bare status.

    A gap in a programme we are not engaged to fill is **not** an opportunity.
    Showing it as one is noise, and noise erodes trust in the gaps that are real.
    """
    out = []
    for claim in claims:
        cell = claim.to_dict()
        scope = engagements.get(claim.program_code)
        cell["engagement_scope"] = scope.value if scope else None
        if scope is EngagementScope.OUT_OF_SCOPE and claim.outcome in {
            Outcome.UNCLAIMED,
            Outcome.NOT_ASSESSED,
        }:
            cell["outcome"] = Outcome.OUT_OF_SCOPE.value
        out.append(cell)
    return out


def group_by_client(claims: list[ProgramClaim]) -> dict[int, list[ProgramClaim]]:
    """Partition by tenant.

    Claims stay partitioned rather than concatenated for the same reason payroll
    rows do: it should take a deliberate act to sum across clients, not an
    accident of iteration order.
    """
    grouped: dict[int, list[ProgramClaim]] = {}
    for claim in claims:
        grouped.setdefault(claim.client_id, []).append(claim)
    return grouped


def situation(claims: list[ProgramClaim]) -> dict[str, Any]:
    """Why you would call this client, as a brief an agent can only narrate.

    Every figure here is computed. The agent is handed this object and told to
    restate it — it never sees payroll, never sees a rule pack, and has nothing
    to add a number to [ADR-004].

    Ordered by `priority_band`, so the first entry is the reason to call. Money
    is a string throughout: a claim figure must not meet a float, and this one
    is going into a sentence somebody reads to a client.
    """
    ranked = sorted(
        claims,
        key=lambda c: (c.priority_band.rank, -float(c.identified_usd), c.tax_year),
    )
    by_band: dict[str, list[dict[str, Any]]] = {}
    for claim in ranked:
        by_band.setdefault(claim.priority_band.value, []).append({
            "program_code": claim.program_code,
            "tax_year": claim.tax_year,
            "identified_usd": str(claim.identified_usd),
            "claimed_usd": str(claim.claimed_usd),
            "opportunity_usd": str(claim.opportunity_usd),
            "net_new_jobs": claim.net_new_jobs,
            "threshold_jobs": claim.threshold_jobs,
            "jobs_margin": claim.jobs_margin,
            "outcome": claim.outcome.value,
            "provenance_verified": claim.provenance.verified,
        })

    lead = ranked[0] if ranked else None
    totals_all = totals(claims)
    return {
        "cells": len(claims),
        "programs": sorted({c.program_code for c in claims}),
        "tax_years": sorted({c.tax_year for c in claims}),
        "lead_band": lead.priority_band.value if lead else None,
        "lead_program": lead.program_code if lead else None,
        "lead_tax_year": lead.tax_year if lead else None,
        "by_band": by_band,
        "identified_usd": totals_all["identified_usd"],
        "opportunity_usd": totals_all["opportunity_usd"],
        "exposure_usd": totals_all["exposure_usd"],
        # The claimed side of this book is seeded, and two of the five bands are
        # derived from it. An agent narrating "they under-claimed by $X" without
        # this would be asserting a filing nobody supplied.
        "claimed_is_unverified": any(not c.provenance.verified for c in claims),
    }
