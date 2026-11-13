"""Turning a request into items, and the preview that states what would happen. Reads no payroll. [ADR-012]

**One item per client by default (`refresh_once`).** A run for one year replays and writes every authored year of the
client's payroll, so asking for "all years" as N client-year items would replay N times for the same result. The item
carries no year and resolves to the client's latest runnable year when it starts. Giving explicit years, or turning
`refresh_once` off with explicit years, makes one item per client-year: each of them replays every year, so the cost
is N times higher, and the preview says so.

**The preview never promises a skip.** Whether data changed is decided when an item starts, because that needs the
year's rows. What is known cheaply (book, manifests) gives an upper bound: a client with no earlier run, or whose
recorded assumption hashes no longer match, cannot be skipped; the rest are candidates only.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from application.runs.errors import BatchTooLarge, RunBatchRefused
from application.runs.selection import Resolution, Scope, resolve_clients, scope_spec, unavailable_among
from config import RunSettings
from domain.runs import BatchKind, RunBatchItem

PREVIEW_ITEMS = 20
#: How many clients' manifests a preview reads. Each is one query on the Warehouse, so it is bounded.
PREVIEW_MANIFEST_READS = 200
_COST_NOTE = "Each run replays every authored year of the client's payroll, whatever year it is asked for."


@dataclass(frozen=True)
class BatchRequest:
    """A validated request to run clients: what, for whom, which years and how."""
    kind: BatchKind
    scope: Scope
    program_code: str | None = None
    tax_years: tuple[int, ...] = ()
    force: bool = False
    include_code_commit: bool = False
    refresh_once: bool = True
    idempotency_key: str | None = None
    override_size_limit: bool = False
    confirm_items: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def validated(self) -> "BatchRequest":
        bad = [y for y in self.tax_years if not 1990 <= int(y) <= 2100]
        if bad:
            raise RunBatchRefused(f"Tax year(s) out of range: {bad}.", "Use four-digit years.")
        if not self.tax_years and not self.refresh_once:
            raise RunBatchRefused(
                "refresh_once is off but no tax years were given.",
                "Name the tax years, or leave refresh_once on to run each client once.",
            )
        return self


def item_count(clients: int, request: BatchRequest) -> int:
    return clients * (len(request.tax_years) if request.tax_years else 1)


def check_size(items: int, request: BatchRequest, settings: RunSettings) -> None:
    from domain.runs import ScopeKind

    if items > settings.max_items:
        can = request.scope.kind is ScopeKind.ALL
        if not (can and request.override_size_limit):
            raise BatchTooLarge(items, settings.max_items, can_override=can)


def make_items(batch_id: str, client_ids: tuple[int, ...], request: BatchRequest) -> list[RunBatchItem]:
    years: tuple[int | None, ...] = tuple(request.tax_years) or (None,)
    items: list[RunBatchItem] = []
    for client_id in client_ids:
        for year in years:
            items.append(RunBatchItem(
                item_id=uuid.uuid4().hex, batch_id=batch_id, client_id=client_id, seq=len(items),
                program_code=request.program_code, tax_year=year,
            ))
    return items


def spec_for(request: BatchRequest, ids: tuple[int, ...]) -> dict[str, Any]:
    spec = scope_spec(request.scope, ids)
    spec.update(
        kind=request.kind.value, program_code=request.program_code, tax_years=list(request.tax_years),
        force=request.force, include_code_commit=request.include_code_commit, refresh_once=request.refresh_once,
    )
    return spec


def _last_run(client_id: int, assumptions: list[dict[str, str]], repo: Any) -> dict[str, Any]:
    manifest = repo.latest(client_id)
    if manifest is None:
        return {"state": "never_run", "can_skip": False, "reason": "no earlier successful run"}
    hashes = {a["sha256"] for a in assumptions}
    recorded = {manifest.step1_assumption_sha256, manifest.onezero_assumption_sha256} - {None, ""}
    known = bool(manifest.calculation_id and manifest.rule_pack_version and recorded)
    matches = known and recorded <= hashes
    return {
        "state": "has_run", "run_id": manifest.run_id, "tax_year": manifest.tax_year,
        "completed_at": manifest.run_completed_at.isoformat() if manifest.run_completed_at else None,
        "can_skip": bool(matches),
        "reason": ("assumption hashes match the last run; the data is checked when the item starts" if matches
                   else "the last run does not record what is needed to compare, or the assumptions changed"),
    }


def _reads(ids: tuple[int, ...], current: list[dict[str, str]], repo: Any) -> dict[int, dict[str, Any]]:
    """Last-run facts for the first `PREVIEW_MANIFEST_READS` clients: one manifest query each, so it is bounded."""
    return {cid: _last_run(cid, current, repo) for cid in ids[:PREVIEW_MANIFEST_READS]}


def preview(
    request: BatchRequest, settings: RunSettings, *, resolution: Resolution | None = None,
    manifests: Callable[[], Any] | None = None, assumptions: Callable[[], list[dict[str, str]]] | None = None,
    portfolio_page: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """What a start would do. Writes nothing and reads no payroll."""
    from application.services import get_run_manifest_repository

    request = request.validated()
    found = resolution or resolve_clients(request.scope)
    items = item_count(len(found.client_ids), request)
    reads = _reads(found.client_ids, (assumptions or _assumptions)(), (manifests or get_run_manifest_repository)())
    complete = len(reads) == len(found.client_ids)
    candidates = 0 if request.force else sum(1 for r in reads.values() if r["can_skip"])
    out = _summary(request, settings, found, reads, items, candidates, complete)
    checked = unavailable_among(found.client_ids, found.names, portfolio_page)
    out.update(unavailable=checked["items"], unavailable_checked=checked["checked"])
    if not checked["checked"]:
        out["notes"].append(f"Which clients are unavailable could not be checked: {checked['reason']}")
    return out


def _summary(
    request: BatchRequest, settings: RunSettings, found: Resolution, reads: dict[int, dict[str, Any]], items: int,
    candidates: int, complete: bool,
) -> dict[str, Any]:
    """The preview's wire shape."""
    return {
        "kind": request.kind.value, "clients": len(found.client_ids), "items": items,
        "years": list(request.tax_years) or "latest runnable year per client",
        "refresh_once": request.refresh_once, "force": request.force,
        "per_client_year_items": len(request.tax_years) > 1,
        "skip_candidates_upper_bound": candidates if complete else None,
        "never_run": sum(1 for r in reads.values() if r["state"] == "never_run"),
        "manifests_read_for": len(reads),
        "requires_confirmation": items > settings.confirm_above, "confirm_above": settings.confirm_above,
        "max_items": settings.max_items, "over_size_limit": items > settings.max_items,
        "first_items": [
            {"client_id": cid, "client_name": found.names.get(cid), "last_run": reads[cid]}
            for cid in found.client_ids[:PREVIEW_ITEMS] if cid in reads
        ],
        "notes": [
            "Whether a client is skipped as unchanged is decided when its item starts; this is an upper bound, not a promise.",
            _COST_NOTE,
        ],
    }


def _assumptions() -> list[dict[str, str]]:
    from application.runs.fingerprint import current_assumptions

    return current_assumptions()
