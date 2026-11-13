"""Offline stand-in for `/api/v2/run-batches`, matching the typed contract in `backend/api/run_batches.py`. Dev tooling.

Stateful and in memory so the Runs page and the start dialog can be driven end to end by the sweeps: a preview, a start,
progress, a failure with a cause, cancel and retry. The data is invented (account numbers, no names, no figures).
"""
from __future__ import annotations

import itertools
import json
import re
from typing import Any

CONFIRM_ABOVE = 25
MAX_ITEMS = 5000
_ids = itertools.count(1)
BATCHES: dict[str, dict[str, Any]] = {}
ITEMS: dict[str, list[dict[str, Any]]] = {}


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    by = {s: 0 for s in ("queued", "running", "succeeded", "skipped", "failed", "cancelled")}
    for i in items:
        s = i["status"]
        key = "running" if s in ("leased", "running") else "skipped" if s.startswith("skipped") else s
        by[key] += 1
    return {"total": len(items), **by}


def _status(counts: dict[str, int]) -> str:
    open_items = counts["queued"] + counts["running"]
    if open_items:
        return "running" if counts["total"] - counts["queued"] else "queued"
    if not counts["failed"] and not counts["cancelled"]:
        return "succeeded"
    return "failed" if counts["failed"] == counts["total"] - counts["cancelled"] and counts["failed"] else "partial"


def _refresh(batch: dict[str, Any]) -> dict[str, Any]:
    items = ITEMS[batch["batch_id"]]
    c = _counts(items)
    batch["counts"] = c
    batch["progress"] = {"done": c["succeeded"] + c["skipped"] + c["failed"] + c["cancelled"], "total": c["total"]}
    batch["status"] = _status(c)
    return batch


def _item(batch_id: str, seq: int, client_id: int, program: str | None, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "item_id": f"{batch_id}-{seq}", "batch_id": batch_id, "seq": seq, "client_id": client_id, "program_code": program,
        "tax_year": 2023, "status": status, "attempts": 1, "run_id": f"run-{client_id}" if status == "succeeded" else None,
        "skip_reason": None, "error_dependency": None, "error_message": None, "not_before": None,
        "started_at": "2026-09-01T10:00:00Z", "finished_at": "2026-09-01T10:00:09Z", **extra,
    }


def _make(batch_id: str, statuses: list[str], **over: Any) -> dict[str, Any]:
    items = []
    for n, status in enumerate(statuses):
        extra: dict[str, Any] = {}
        if status == "failed":
            extra = {"error_dependency": "gold_write", "error_message": "The Gold write did not validate. It is retried once with no other worker on the client."}
        if status == "skipped_unchanged":
            extra = {"skip_reason": "calculation fingerprint, assumption hashes and rule pack are identical to the last run"}
        items.append(_item(batch_id, n, 2001 + n, "GA_JTC", status, **extra))
    ITEMS[batch_id] = items
    batch = {
        "batch_id": batch_id, "kind": "calculate", "scope_kind": "list", "scope_spec": {"client_count": len(items)},
        "program_code": None, "tax_years": [], "force": False, "skip_unchanged": False, "include_code_commit": False,
        "refresh_once": True, "cancel_requested": False, "requested_by": "operator@example.test",
        "requested_at": "2026-09-01T09:59:00Z", "started_at": "2026-09-01T10:00:00Z", "finished_at": "2026-09-01T10:02:00Z",
        "idempotency_key": None, "dry_run_summary": {}, "idempotent_replay": False, "degraded": [], **over,
    }
    BATCHES[batch_id] = _refresh(batch)
    return BATCHES[batch_id]


def _seed() -> None:
    if BATCHES:
        return
    _make("b-done", ["succeeded"] * 4 + ["skipped_unchanged"])
    _make("b-partial", ["succeeded", "succeeded", "failed", "skipped_no_payroll"])
    _make("b-running", ["succeeded", "running", "queued", "queued"], finished_at=None)


def _preview(body: dict[str, Any]) -> dict[str, Any]:
    scope = body.get("scope") or {}
    ids = scope.get("client_ids") or []
    clients = len(ids) if scope.get("kind") in ("one", "list") else 5
    years = body.get("tax_years") or []
    items = clients * (len(years) or 1)
    skip = bool(body.get("skip_unchanged")) and not body.get("force")
    return {
        "kind": body.get("kind", "calculate"), "clients": clients, "items": items,
        "years": years or "latest runnable year per client", "refresh_once": body.get("refresh_once", True),
        "force": bool(body.get("force")), "skip_unchanged": bool(body.get("skip_unchanged")),
        "skip_coverage": "cannot_tell_yet", "per_client_year_items": len(years) > 1,
        "skip_candidates_upper_bound": 0 if skip else 0, "never_run": 1, "manifests_read_for": clients,
        "requires_confirmation": items > CONFIRM_ABOVE, "confirm_above": CONFIRM_ABOVE, "max_items": MAX_ITEMS,
        "over_size_limit": items > MAX_ITEMS, "programs": {"GA_JTC": items}, "multi_program_clients": 0, "program_items": items,
        "first_items": [{"client_id": 2001 + n, "client_name": None, "last_run": {"state": "never_run"}} for n in range(min(clients, 5))],
        "unavailable": [], "unavailable_checked": True,
        "notes": ["Nothing is skipped: every item runs." if not skip else "Whether a client is skipped is decided when its item starts.",
                  "Each run replays every authored year of the client's payroll, whatever year it is asked for."],
    }


def _start(body: dict[str, Any]) -> tuple[int, Any]:
    prev = _preview(body)
    if prev["requires_confirmation"] and body.get("confirm_items") != prev["items"]:
        return 409, {"detail": {"code": "confirmation_required", "message": f"This starts {prev['items']} runs.",
                                "remedy": f"Send confirm_items={prev['items']}."}}
    batch_id = f"b-new-{next(_ids)}"
    batch = _make(batch_id, ["queued"] * max(prev["items"], 1), kind=body.get("kind", "calculate"), started_at=None, finished_at=None,
                  skip_unchanged=bool(body.get("skip_unchanged")), requested_at="2026-09-01T10:05:00Z")
    return 202, batch


def route(method: str, path: str, query: dict[str, list[str]], body: bytes):
    """A JSON-able body (or `(status, body)`) for a run-batch path, else None."""
    if not path.startswith("/api/v2/run-batches"):
        return None
    _seed()
    rest = path[len("/api/v2/run-batches"):].strip("/")
    payload = json.loads(body) if body else {}
    if not rest and method == "POST":
        return (200, {"dry_run": True, "preview": _preview(payload)}) if payload.get("dry_run") else _start(payload)
    if not rest:
        status = (query.get("status") or [None])[0]
        rows = [b for b in reversed(list(BATCHES.values())) if not status or b["status"] == status]
        return {"items": rows, "total": len(rows), "limit": 25, "offset": 0}
    m = re.fullmatch(r"([^/]+)(?:/(items|cancel|retry-failed))?", rest)
    if not m or m.group(1) not in BATCHES:
        return 404, {"detail": "unknown batch"}
    batch, action = BATCHES[m.group(1)], m.group(2)
    if action == "items":
        status = (query.get("status") or [None])[0]
        rows = [i for i in ITEMS[batch["batch_id"]] if not status or i["status"] == status]
        return {"items": rows, "total": len(rows), "limit": 50, "offset": 0}
    if action == "cancel":
        n = 0
        for i in ITEMS[batch["batch_id"]]:
            if i["status"] == "queued":
                i["status"], n = "cancelled", n + 1
        batch["cancel_requested"] = True
        return _refresh(batch) | {"cancelled_now": n}
    if action == "retry-failed":
        n = 0
        for i in ITEMS[batch["batch_id"]]:
            if i["status"] == "failed":
                i.update(status="queued", error_dependency=None, error_message=None)
                n += 1
        return _refresh(batch) | {"requeued": n}
    return _refresh(batch)
