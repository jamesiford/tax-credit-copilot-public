"""Turning a request into items, and the preview that states what would happen. Reads no payroll. [ADR-012]

**One item per client by default (`refresh_once`).** A run for one year replays and writes every authored year of the
client's payroll, so asking for "all years" as N client-year items would replay N times for the same result. The item
carries no year and resolves to the client's latest runnable year when it starts. Giving explicit years, or turning
`refresh_once` off with explicit years, makes one item per client-year: each of them replays every year, so the cost
is N times higher, and the preview says so.

**Skipping is opt-in (`skip_unchanged`, default off) and the preview never promises one.** Whether data changed is
decided when an item starts, because that needs the client's payroll. What is known cheaply (book, manifests) gives an
upper bound: a client with no earlier run, whose manifest carries no client-wide fingerprint (`source_snapshot_id`), or
whose recorded assumption hashes no longer match, cannot be skipped; the rest are candidates only. [F04b.1]

**One item per (client, program).** A client with payroll in several calculable programs is run for each. [F04b.4]
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from application.runs.errors import BatchTooLarge, RunBatchRefused
from application.runs.pairs import client_pairs, pair_summary
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
    skip_unchanged: bool = False
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


def item_count(pairs: list[tuple[int, str | None]], request: BatchRequest) -> int:
    """Items a batch queues: one per (client, program), times the explicit years if any."""
    return len(pairs) * (len(request.tax_years) if request.tax_years else 1)


def check_size(items: int, request: BatchRequest, settings: RunSettings) -> None:
    from domain.runs import ScopeKind

    if items > settings.max_items:
        can = request.scope.kind is ScopeKind.ALL
        if not (can and request.override_size_limit):
            raise BatchTooLarge(items, settings.max_items, can_override=can)


def make_items(batch_id: str, pairs: list[tuple[int, str | None]], request: BatchRequest) -> list[RunBatchItem]:
    years: tuple[int | None, ...] = tuple(request.tax_years) or (None,)
    items: list[RunBatchItem] = []
    for client_id, program in pairs:
        for year in years:
            items.append(RunBatchItem(
                item_id=uuid.uuid4().hex, batch_id=batch_id, client_id=client_id, seq=len(items),
                program_code=program, tax_year=year,
            ))
    return items


def spec_for(request: BatchRequest, ids: tuple[int, ...], pairs: list[tuple[int, str | None]] | None = None) -> dict[str, Any]:
    spec = scope_spec(request.scope, ids)
    spec.update(
        kind=request.kind.value, program_code=request.program_code, tax_years=list(request.tax_years),
        force=request.force, skip_unchanged=request.skip_unchanged, include_code_commit=request.include_code_commit,
        refresh_once=request.refresh_once, **({"program_items": len(pairs)} if pairs is not None else {}),
    )
    return spec


def _last_run(client_id: int, assumptions: list[dict[str, str]], repo: Any) -> dict[str, Any]:
    manifest = repo.latest(client_id)
    if manifest is None:
        return {"state": "never_run", "can_skip": False, "reason": "no earlier successful run"}
    hashes = {a["sha256"] for a in assumptions}
    recorded = {manifest.step1_assumption_sha256, manifest.onezero_assumption_sha256} - {None, ""}
    covers_all_years = bool(getattr(manifest, "source_snapshot_id", None))
    known = bool(manifest.calculation_id and manifest.rule_pack_version and recorded and covers_all_years)
    matches = known and recorded <= hashes
    return {
        "state": "has_run", "run_id": manifest.run_id, "tax_year": manifest.tax_year,
        "completed_at": manifest.run_completed_at.isoformat() if manifest.run_completed_at else None,
        "can_skip": bool(matches), "coverage": "all_years" if covers_all_years else "cannot_tell_yet",
        "reason": ("assumption hashes match the last run; the data is checked when the item starts" if matches
                   else "the last run does not record a client-wide data fingerprint or what is needed to compare, "
                        "or the assumptions changed"),
    }


def _reads(ids: tuple[int, ...], current: list[dict[str, str]], repo: Any) -> dict[int, dict[str, Any]]:
    """Last-run facts for the first `PREVIEW_MANIFEST_READS` clients: one manifest query each, so it is bounded."""
    return {cid: _last_run(cid, current, repo) for cid in ids[:PREVIEW_MANIFEST_READS]}


def preview(
    request: BatchRequest, settings: RunSettings, *, resolution: Resolution | None = None,
    manifests: Callable[[], Any] | None = None, assumptions: Callable[[], list[dict[str, str]]] | None = None,
    portfolio_page: Callable[[], dict[str, Any]] | None = None, footprint: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """What a start would do. Writes nothing and reads no payroll."""
    from application.services import get_run_manifest_repository

    request = request.validated()
    found = resolution or resolve_clients(request.scope)
    pairs = client_pairs(found.client_ids, request.program_code, footprint)
    items = item_count(pairs, request)
    reads = _reads(found.client_ids, (assumptions or _assumptions)(), (manifests or get_run_manifest_repository)())
    complete = len(reads) == len(found.client_ids)
    skipping = request.skip_unchanged and not request.force
    candidates = sum(1 for r in reads.values() if r["can_skip"]) if skipping else 0
    out = _summary(request, settings, found, reads, items, candidates, complete)
    out.update(pair_summary(pairs), program_items=len(pairs))
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
        "refresh_once": request.refresh_once, "force": request.force, "skip_unchanged": request.skip_unchanged,
        "skip_coverage": _coverage(reads),
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
            "Whether a client is skipped as unchanged is decided when its item starts; this is an upper bound, not a promise."
            if request.skip_unchanged and not request.force else "Nothing is skipped: every item runs.",
            _COST_NOTE,
        ],
    }


def _coverage(reads: dict[int, dict[str, Any]]) -> str:
    """`all_years` when every earlier run recorded the client-wide fingerprint, `cannot_tell_yet` when none did, else `mixed`."""
    found = {r["coverage"] for r in reads.values() if "coverage" in r}
    return "none_yet" if not found else found.pop() if len(found) == 1 else "mixed"


def _assumptions() -> list[dict[str, str]]:
    from application.runs.fingerprint import current_assumptions

    return current_assumptions()
