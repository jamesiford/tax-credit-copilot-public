"""Offline stand-in for `/api/v2/programs` and `/api/v2/program-drafts`, matching the typed models in `backend/api/programs.py`
and `backend/api/program_draft_models.py`. Dev tooling, not shipped. [F07.2]

Stateful and in memory so the Program manager pages can be driven end to end by the sweeps: a catalog with a calculable program,
a second calculable program in the SAME state (so the program picker has something to pick), a described program with blockers,
and drafts in each status. `backend/tests/test_mock_api_contract.py` compares every payload built here with the backend response
models, so this file cannot drift from them. The data is invented: fictional program codes, no client, no statute value that
anyone has checked. Every program and draft says it is not verified.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
from typing import Any

NOT_VERIFIED = "not_verified"
_NOTE = "Every program here is reported as encoded; none is verified or legally confirmed."
_ids = itertools.count(1)
DRAFTS: dict[str, dict[str, Any]] = {}
EVENTS: dict[str, list[dict[str, Any]]] = {}


def _program(code: str, name: str, state: str | None, years: list[int], unverified: list[int], reason: str, level: str = "state") -> dict[str, Any]:
    calculable = bool(years)
    return {
        "code": code, "name": name, "state": state, "jurisdiction": {"level": level, "code": state or "US"},
        "lifecycle": "calculable" if calculable else "described", "authored_years": years, "unverified_years": unverified,
        "verification": NOT_VERIFIED, "calculable": calculable, "not_calculable_reason": "" if calculable else reason,
        "engagement": {"in_scope": 3, "out_of_scope": 1, "prospective": 1, "clients": 5} if calculable else {"in_scope": 0, "out_of_scope": 0, "prospective": 0, "clients": 0},
    }


PROGRAMS: list[dict[str, Any]] = [
    _program("ZZ_DEMO_JTC", "Demo jobs credit (fictional)", "GA", [2023, 2024, 2025], [2025], ""),
    _program("ZZ_DEMO_SECOND", "Second demo credit in the same state (fictional)", "GA", [2024, 2025], [2024, 2025], ""),
    _program("ZZ_DEMO_NEXT", "Demo credit awaiting statute (fictional)", "NC", [], [], "No tax year pack has been authored for this program."),
    _program("ZZ_DEMO_FED", "Demo federal credit (fictional)", None, [], [], "Federal programs are described, not calculated.", level="federal"),
]


def _issue(severity: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "path": path, "message": message}


def _detail(program: dict[str, Any]) -> dict[str, Any]:
    code = program["code"]
    years = [{"tax_year": y, "rule_pack_version": f"{code.lower()}-{y}", "unverified": y in program["unverified_years"],
              "source": "authored in git", "issues": [_issue("info", "prototype_flag", "_prototype_verify", "Flagged: not verified.")] if y in program["unverified_years"] else []}
             for y in program["authored_years"]]
    pack_issues = [] if program["calculable"] else [_issue("warning", "no_year_pack", "$", "No year pack is authored yet.")]
    return program | {
        "pack": {"file": f"rules/{code.lower()}.json", "present": True, "rule_pack_version": f"{code.lower()}-base", "credit_name": program["name"],
                 "citation": "Citation to be supplied", "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"}, "notes": "Invented for the sweeps."},
        "years": years,
        "validation": {"pack": pack_issues, "error_count": 0, "valid": True},
        "blockers": [] if program["calculable"] else [program["not_calculable_reason"]],
    }


def catalog() -> dict[str, Any]:
    return {"programs": PROGRAMS, "total": len(PROGRAMS), "engagement_available": True, "verification_note": _NOTE}


def _finding(file: str, severity: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"file": file, "severity": severity, "code": code, "path": path, "message": message}


def _validation(draft: dict[str, Any]) -> dict[str, Any]:
    findings = [] if draft["status"] != "draft" else [_finding("pack", "error", "missing_citation", "$.credit.citation", "The citation is empty.")]
    errors = sum(f["severity"] == "error" for f in findings)
    return {"content_sha256": draft["content_sha256"], "valid": errors == 0, "errors": errors, "warnings": 0, "infos": 0,
            "findings": findings, "truncated": False, "verification": NOT_VERIFIED}


def _sha(documents: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(documents, sort_keys=True).encode()).hexdigest()


def _actions(status: str, valid: bool) -> list[str]:
    actions: list[str] = []
    if status in ("draft", "needs_changes"):
        actions += ["edit", "validate"] + (["request_review"] if valid else [])
    if status == "ready_for_review":
        actions += ["approve", "request_changes"]
    if status in ("approved_for_export", "exported"):
        actions.append("export")
    if status != "withdrawn":
        actions.append("preview")
    if status not in ("withdrawn", "exported"):
        actions.append("withdraw")
    return actions


def _make(code: str, name: str, status: str, **over: Any) -> dict[str, Any]:
    n = next(_ids)
    draft_id = f"d-{n}"
    documents = {"pack": {"credit": {"name": name, "citation": ""}}, "years": {"2025": {"tax_year": 2025, "_prototype_verify": True}}}
    draft = {
        "draft_id": draft_id, "proposed_code": code, "name": name, "jurisdiction_level": "state", "state": "NC", "status": status, "version": 1,
        "created_by": "writer-a", "created_at": "2026-09-01T09:00:00Z", "updated_by": "writer-a", "updated_at": "2026-09-01T09:30:00Z",
        "pack_file": f"rules/{code.lower()}.json", "validation_errors": None, "verification": NOT_VERIFIED, "has_runtime_authority": False,
        "documents": documents, "content_sha256": _sha(documents), "validation": None, "validation_current": False,
        "review": {"requested_by": None, "reviewer": None, "decision": None, "comment": None, "decided_at": None, "approved_sha256": None},
        "export": {"exported_at": None, "bundle_sha256": None}, "allowed_actions": [], "events": [],
    } | over
    DRAFTS[draft_id] = draft
    EVENTS[draft_id] = [{"seq": 1, "event_type": "created", "actor": "writer-a", "at": "2026-09-01T09:00:00Z", "from_status": None, "to_status": "draft", "detail": {}}]
    return _refresh(draft)


def _refresh(draft: dict[str, Any]) -> dict[str, Any]:
    validation = draft["validation"]
    draft["validation_errors"] = None if validation is None else validation["errors"]
    draft["validation_current"] = bool(validation) and validation["content_sha256"] == draft["content_sha256"]
    draft["allowed_actions"] = _actions(draft["status"], draft["validation_current"] and bool(validation and validation["valid"]))
    draft["events"] = EVENTS[draft["draft_id"]]
    return draft


def _seed() -> None:
    if DRAFTS:
        return
    _make("ZZ_DEMO_NEXT", "Demo credit awaiting statute", "draft")
    ready = _make("ZZ_DEMO_READY", "Demo credit ready for review", "ready_for_review")
    ready["validation"] = _validation(ready | {"status": "ready"})
    ready["review"]["requested_by"] = "writer-a"
    _refresh(ready)
    approved = _make("ZZ_DEMO_DONE", "Demo credit approved", "approved_for_export")
    approved["validation"] = _validation(approved | {"status": "ready"})
    approved["review"] |= {"requested_by": "writer-a", "reviewer": "writer-b", "decision": "approve", "decided_at": "2026-09-02T10:00:00Z", "approved_sha256": approved["content_sha256"]}
    _refresh(approved)


def _summary(draft: dict[str, Any]) -> dict[str, Any]:
    keys = ("draft_id", "proposed_code", "name", "jurisdiction_level", "state", "status", "version", "created_by", "created_at", "updated_by",
            "updated_at", "pack_file", "validation_errors", "verification", "has_runtime_authority")
    return {k: draft[k] for k in keys}


def _event(draft: dict[str, Any], kind: str, to: str | None = None, **detail: Any) -> None:
    log = EVENTS[draft["draft_id"]]
    log.append({"seq": len(log) + 1, "event_type": kind, "actor": "writer-a", "at": "2026-09-03T08:00:00Z", "from_status": draft["status"], "to_status": to or draft["status"], "detail": detail})
    if to:
        draft["status"] = to
    draft["version"] += 1
    _refresh(draft)


def _manifest(draft: dict[str, Any]) -> dict[str, Any]:
    files = [{"path": draft["pack_file"], "sha256": _sha(draft["documents"]["pack"]), "bytes": 120}]
    return {"kind": "program-draft-bundle", "schema_version": 1, "draft_id": draft["draft_id"], "proposed_code": draft["proposed_code"], "name": draft["name"],
            "state": draft["state"], "content_sha256": draft["content_sha256"], "approved_sha256": draft["review"]["approved_sha256"], "verification": NOT_VERIFIED,
            "has_runtime_authority": False, "changelog_line": f"Added program {draft['proposed_code']} (not verified).", "files": files,
            "bundle_sha256": _sha({"files": files}), "bundle_bytes": 512}


def _preview(draft: dict[str, Any]) -> dict[str, Any]:
    return {"label": "Preview, not verified, not for filing", "draft_id": draft["draft_id"], "proposed_code": draft["proposed_code"], "state": draft["state"],
            "dataset": {"kind": "synthetic_sample", "employees": 40}, "unverified": True, "unverified_flags": 1,
            "years": [{"tax_year": 2025, "average_headcount": 41.5, "prior_average_headcount": 38.0, "is_base_year": False, "threshold_jobs": 2.0,
                       "qualifying_jobs": 3.5, "per_job_usd": 1000.0, "annual_credit_usd": 3500.0, "benefit_period_years": 3, "rows_used": 480, "months_with_payroll": 12,
                       "window": "2025-01-01..2025-12-31"}],
            "declined": [], "persisted": False, "wrote_nothing": True}


def _draft_route(method: str, rest: str, query: dict[str, list[str]], payload: dict[str, Any]):
    if not rest:
        if method == "POST":
            draft = _make(payload.get("code", "ZZ_NEW"), payload.get("name", "New program"), "draft", state=payload.get("state", "NC"))
            return 201, draft
        status = (query.get("status") or [None])[0]
        rows = [_summary(d) for d in reversed(list(DRAFTS.values())) if not status or d["status"] == status]
        return {"items": rows, "total": len(rows), "limit": 50, "offset": 0}
    m = re.fullmatch(r"([^/]+)(?:/(documents|validate|request-review|review|preview|withdraw|export(?:/manifest)?))?", rest)
    if not m or m.group(1) not in DRAFTS:
        return 404, {"detail": {"code": "draft_not_found", "reason": "no such draft"}}
    draft, action = DRAFTS[m.group(1)], m.group(2)
    if action is None:
        return draft
    if action == "export/manifest":
        return _manifest(draft)
    if action == "preview":
        return _preview(draft)
    if action == "export":
        _event(draft, "exported", "exported") if draft["status"] == "approved_for_export" else None
        return 200, b"PK\x03\x04 mock bundle"
    if action == "documents":
        if payload.get("expected_version") != draft["version"]:
            return 409, {"detail": {"code": "draft_conflict", "reason": "The draft changed since you read it."}}
        draft["documents"] = {"pack": payload.get("pack") or draft["documents"]["pack"], "years": payload.get("years") or draft["documents"]["years"]}
        draft["content_sha256"] = _sha(draft["documents"])
        _event(draft, "documents_edited")
    elif action == "validate":
        draft["validation"] = _validation(draft)
        _event(draft, "validated")
    elif action == "request-review":
        _event(draft, "review_requested", "ready_for_review")
    elif action == "review":
        approve = payload.get("decision") == "approve"
        draft["review"] |= {"decision": payload.get("decision"), "comment": payload.get("comment"), "reviewer": "writer-b"}
        _event(draft, "reviewed", "approved_for_export" if approve else "needs_changes")
    elif action == "withdraw":
        _event(draft, "withdrawn", "withdrawn")
    return draft


def route(method: str, path: str, query: dict[str, list[str]], body: bytes):
    """A JSON-able body (or `(status, body)`) for a program or draft path, else None."""
    if path == "/api/v2/programs":
        return catalog()
    m = re.fullmatch(r"/api/v2/programs/([^/]+)", path)
    if m:
        program = next((p for p in PROGRAMS if p["code"] == m.group(1)), None)
        return _detail(program) if program else (404, {"detail": f"no program {m.group(1)!r} in the registry"})
    if not path.startswith("/api/v2/program-drafts"):
        return None
    _seed()
    payload = json.loads(body) if body else {}
    return _draft_route(method, path[len("/api/v2/program-drafts"):].strip("/"), query, payload)
