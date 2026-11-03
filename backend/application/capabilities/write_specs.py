"""What each channel write is, and how to preview it. [CH-05]

A `WriteSpec` pairs the two things a prepare/commit flow needs for one write:

- `build(principal, args)` makes the SAME mediator command the commit will send,
  authored by the person (never the gateway). Building it is also validation, so a
  request the command would refuse fails at prepare, before a token exists.
- `preview(command)` reads the current state and derives the proposed state from
  the command's own pure functions (`build_claim`, `next_claim`, `plan_base_year`
  ...), so the preview and the committed row are the same computation, not two
  that could drift.

Previews write nothing. Figures come from the engine and the stores; none is
produced here.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from application.identity import Principal
from application.mediator import Command
from domain.claims import ClaimStatus, EngagementScope, Provenance

FINDING_RESOLUTIONS = ("accept", "assign", "drop", "flag")


class InvalidWrite(ValueError):
    """The request is malformed; no token is minted for it."""


def _need(args: Mapping[str, Any], name: str, kind: type) -> Any:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, kind):
        raise InvalidWrite(f"{name} is required and must be {kind.__name__}")
    return value


def _enum(enum: type, value: Any, name: str):
    try:
        return enum(value)
    except ValueError as exc:
        raise InvalidWrite(f"{name} must be one of {[e.value for e in enum]}") from exc


def _claim_view(claim: Any) -> dict[str, Any] | None:
    if claim is None:
        return None
    d = claim.to_dict()
    keys = ("status", "provenance", "identified_usd", "claimed_usd", "certified_usd",
            "decline_reason", "decided_by", "filing_reference")
    return {k: d.get(k) for k in keys}


@dataclass(frozen=True)
class WriteSpec:
    base: str
    summary: str
    build: Callable[[Principal, Mapping[str, Any]], Command]
    preview: Callable[[Command], dict[str, Any]]


# ------------------------------------------------------------------ findings


def _finding_now(client_id: int, tax_year: int | None, finding_id: str) -> dict[str, Any] | None:
    from application.wiring import get_finding_repository

    live = get_finding_repository().live(client_id, tax_year)
    match = next((r for r in live if r.finding_id == finding_id), None)
    return None if match is None else {"resolution": match.resolution, "note": match.note,
                                       "decided_by": match.decided_by}


def _build_resolve(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.resolve_finding import ResolveFindingCommand

    resolution = a.get("resolution")
    if resolution not in FINDING_RESOLUTIONS:
        raise InvalidWrite(f"resolution must be one of {list(FINDING_RESOLUTIONS)}")
    return ResolveFindingCommand(
        actor=principal.actor, finding_id=_need(a, "finding_id", str), client_id=_need(a, "client_id", int),
        tax_year=_need(a, "tax_year", int), resolution=resolution,
        keep_worksite=a.get("keep_worksite"), note=a.get("note"),
    )


def _preview_resolve(c: Any) -> dict[str, Any]:
    return {
        "before": _finding_now(c.client_id, c.tax_year, c.finding_id),
        "after": {"finding_id": c.finding_id, "resolution": c.resolution, "note": c.note,
                  "decided_by": c.actor},
    }


def _build_reopen(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.resolve_finding import ReopenFindingCommand

    return ReopenFindingCommand(
        actor=principal.actor, finding_id=_need(a, "finding_id", str), client_id=_need(a, "client_id", int),
    )


def _preview_reopen(c: Any) -> dict[str, Any]:
    return {
        "before": _finding_now(c.client_id, None, c.finding_id),
        "after": {"finding_id": c.finding_id, "resolution": None, "requires_decision": True},
    }


# -------------------------------------------------------------------- claims


def _build_transition(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.transition_claim import TransitionClaimCommand

    return TransitionClaimCommand(
        actor=principal.actor, client_id=_need(a, "client_id", int),
        program_code=_need(a, "program_code", str), tax_year=_need(a, "tax_year", int),
        status=_enum(ClaimStatus, a.get("status"), "status"), decline_reason=a.get("decline_reason"),
    )


def _preview_transition(c: Any) -> dict[str, Any]:
    from application.commands.transition_claim import current_claim, next_claim

    current = current_claim(c)
    return {"before": _claim_view(current), "after": _claim_view(next_claim(current, c))}


def _build_record(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.record_claim import RecordClaimCommand

    # A claim typed into a chat is somebody's word, never a filing: the
    # provenance is fixed, not an argument.
    return RecordClaimCommand(
        actor=principal.actor, client_id=_need(a, "client_id", int),
        program_code=_need(a, "program_code", str), tax_year=_need(a, "tax_year", int),
        status=_enum(ClaimStatus, a.get("status"), "status"), provenance=Provenance.CLIENT_ASSERTED,
    )


def _preview_record(c: Any) -> dict[str, Any]:
    from application.commands.record_claim import build_claim
    from application.wiring import get_claim_repository

    current = get_claim_repository().current(c.client_id, c.program_code, c.tax_year)
    return {"before": _claim_view(current), "after": _claim_view(build_claim(c))}


# ----------------------------------------------------------------- engagement


def _build_engagement(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.set_engagement import SetEngagementCommand

    return SetEngagementCommand(
        actor=principal.actor, client_id=_need(a, "client_id", int),
        program_code=_need(a, "program_code", str), scope=_enum(EngagementScope, a.get("scope"), "scope"),
        note=a.get("note"),
    )


def _preview_engagement(c: Any) -> dict[str, Any]:
    from application.wiring import get_claim_repository

    held = next((e for e in get_claim_repository().engagements(c.client_id)
                 if e.program_code == c.program_code.upper()), None)
    return {
        "before": None if held is None else {"scope": held.scope.value, "note": held.note, "set_by": held.set_by},
        "after": {"scope": c.scope.value, "note": c.note, "set_by": c.actor},
    }


# ------------------------------------------------------------------ base year


def _build_base_year(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.set_base_year import SetBaseYearCommand

    return SetBaseYearCommand(
        actor=principal.actor, client_id=_need(a, "client_id", int),
        worksite_id=_need(a, "unit_id", str), base_year=_need(a, "base_year", int),
    )


def _preview_base_year(c: Any) -> dict[str, Any]:
    from application.commands.set_base_year import plan_base_year
    from application.queries.rebase_unit import RebaseUnitQuery
    from application.wiring import get_mediator

    plan = plan_base_year(c)
    rebase = get_mediator().send(RebaseUnitQuery(
        client_id=c.client_id, worksite_id=c.worksite_id, base_year=c.base_year, state=c.state,
    ))
    return {
        "before": {"base_year": plan.saved if plan.saved is not None else plan.current_base},
        "after": {
            "base_year": c.base_year,
            "total_annual_credit_usd": rebase["total_annual_credit_usd"],
            "run_total_annual_credit_usd": rebase["run_total_annual_credit_usd"],
            "delta_annual_credit_usd": rebase["delta_annual_credit_usd"],
        },
    }


# ------------------------------------------------------------- claim package


def _build_package(principal: Principal, a: Mapping[str, Any]) -> Command:
    from application.commands.create_claim_package import CreateClaimPackageCommand

    return CreateClaimPackageCommand(
        actor=principal.actor, client_id=_need(a, "client_id", int), tax_year=_need(a, "tax_year", int),
    )


def _preview_package(c: Any) -> dict[str, Any]:
    from application.capabilities.errors import NotCalculated
    from application.claim_package import SHEETS
    from application.claim_package_service import latest_package
    from application.wiring import get_claim_package_source

    run = get_claim_package_source().latest_run(c.client_id)
    if run is None:
        raise NotCalculated(f"client {c.client_id} has no completed calculation run to package")
    earlier = latest_package(c.client_id, c.tax_year)
    return {
        "before": None if earlier is None else {"file_name": earlier.file_name, "run_id": earlier.run_id},
        "after": {"run_id": str(run["run_id"]), "tax_year": c.tax_year, "sheets": ", ".join(SHEETS)},
    }


SPECS: dict[str, WriteSpec] = {spec.base: spec for spec in (
    WriteSpec("finding_resolve", "Record a decision about a finding.", _build_resolve, _preview_resolve),
    WriteSpec("finding_reopen", "Withdraw a decision on a finding.", _build_reopen, _preview_reopen),
    WriteSpec("claim_transition", "Move a claim along its lifecycle.", _build_transition, _preview_transition),
    WriteSpec("claim_record", "Record an unverified claim.", _build_record, _preview_record),
    WriteSpec("engagement_set", "Set the engagement for a programme.", _build_engagement, _preview_engagement),
    WriteSpec("base_year_set", "Set a location's base year.", _build_base_year, _preview_base_year),
    WriteSpec("claim_package_create", "Build the claim package.", _build_package, _preview_package),
)}
