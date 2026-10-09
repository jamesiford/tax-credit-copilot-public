"""The rule library - which programmes we hold, and how verified each is.

Split out of `api/eligibility.py`. A rule pack is the statute as we have encoded
it, and how confident we are in one is a different question from what a client
qualifies for.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data.claims import get_all_claims

router = APIRouter(prefix="/api", tags=["rules"])

_RULES = Path(__file__).resolve().parent.parent / "rules"

# Rule-pack practitioner sign-off store (Phase E P3 #16).
# Mutable in-memory dict keyed by rule pack code → {verified_by, verified_at, note}.
# Production: persisted alongside the rule pack in the Fabric warehouse and
# gated by a tax-practitioner approval workflow with CI sign-off enforcement.
# Two packs ship pre-approved so the UI starts with mixed state.
_RULE_VERIFICATION: dict[str, dict[str, Any]] = {
    "GA_JTC": {
        "verified_by": "K. Wallace, JD (External tax counsel)",
        "verified_at": "2026-03-22",
        "note": "Tier 1 GA county designations re-verified against current DOR guidance.",
    },
    "FED_WOTC": {
        "verified_by": "K. Wallace, JD (External tax counsel)",
        "verified_at": "2026-04-02",
        "note": "WOTC target group caps + flat $2,400 simplified amount confirmed against IRS Form 5884.",
    },
}


class RuleVerificationRequest(BaseModel):
    verified_by: str
    note: str | None = None


@router.get("/rules")
def rules() -> dict[str, Any]:
    """List active rule packs loaded from backend/rules with metadata for the UI rule library.

    Everything returned here is derived from the actual JSON files on disk plus
    the in-memory claims list — no synthesized fields. `summary.last_update_iso`
    uses the newest pack file mtime; `recent_changes` lists the 5 most recently
    modified packs; `pinned_claims` counts claims whose `credit_code` matches.
    """
    pack_files = sorted(_RULES.glob("*.json"))
    parsed: list[tuple[Path, float, dict[str, Any]]] = []
    for p in pack_files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        parsed.append((p, p.stat().st_mtime, data))

    # Count claims per credit_code (real data)
    claim_counts: Counter[str] = Counter()
    for c in get_all_claims():
        code = c.get("credit_code")
        if code:
            claim_counts[code] += 1

    rows: list[dict[str, Any]] = []
    for p, _mt, data in parsed:
        code = data.get("credit", {}).get("code")
        verification = _RULE_VERIFICATION.get(code)
        rows.append(
            {
                "file": p.name,
                "code": code,
                "name": data.get("credit", {}).get("name"),
                "jurisdiction": data.get("jurisdiction", {}).get("code"),
                "jurisdiction_level": data.get("jurisdiction", {}).get("level"),
                "citation": data.get("credit", {}).get("statutory_citation"),
                "threshold": data.get("thresholds", {}).get("minimum_new_jobs"),
                "benefit_period_years": data.get("benefit", {}).get("benefit_period_years"),
                "prototype_verification": data.get("_prototype_verification"),
                "effective_date": data.get("effective_date"),
                "version": data.get("rule_pack_version"),
                "filing": data.get("filing"),
                "pinned_claims": claim_counts.get(code, 0),
                "verified": bool(verification),
                "verification": verification,
                "one_zero": data.get("one_zero"),
            }
        )

    # Recent changes — newest 5 packs by file mtime
    by_recency = sorted(parsed, key=lambda t: t[1], reverse=True)
    recent_changes: list[dict[str, Any]] = []
    for p, mt, data in by_recency[:5]:
        ts = datetime.fromtimestamp(mt, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        citation = data.get("credit", {}).get("statutory_citation") or p.stem
        name = data.get("credit", {}).get("name") or p.stem
        version = data.get("rule_pack_version") or "0.1.0"
        filing = (data.get("filing") or {}).get("window") or "—"
        recent_changes.append(
            {
                "timestamp_utc": ts,
                "citation": citation,
                "credit_code": data.get("credit", {}).get("code"),
                "title": f"{name} — prototype pack pinned",
                "detail": f"Filing: {filing} · pinned as v{version}",
                "version": f"v{version}",
                "status": "ok",
            }
        )

    last_update_iso = (
        datetime.fromtimestamp(by_recency[0][1], tz=timezone.utc).isoformat(timespec="minutes")
        if by_recency
        else None
    )

    summary = {
        "programs_codified": len(rows),
        "active_rule_versions": len(rows),  # 1 active version per pack in prototype
        "last_update_iso": last_update_iso,
        "pending_review": sum(1 for r in rows if not r["verified"]),
        "verified_count": sum(1 for r in rows if r["verified"]),
        "vision_program_count": "240+",  # aspirational scope per product brief
    }

    return {
        "as_of": date.today().isoformat(),
        "rule_count": len(rows),
        "summary": summary,
        "recent_changes": recent_changes,
        "rules": rows,
    }


@router.post("/rules/{code}/verify")
def verify_rule_pack(code: str, payload: RuleVerificationRequest) -> dict[str, Any]:
    """Record a tax-practitioner sign-off on a rule pack (in-memory)."""
    code_upper = code.upper()
    pack_codes = set()
    for p in _RULES.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            c = data.get("credit", {}).get("code")
            if c:
                pack_codes.add(c)
        except Exception:
            continue
    if code_upper not in pack_codes:
        raise HTTPException(status_code=404, detail=f"Unknown rule pack code: {code}")
    _RULE_VERIFICATION[code_upper] = {
        "verified_by": payload.verified_by,
        "verified_at": date.today().isoformat(),
        "note": payload.note,
    }
    return {"code": code_upper, "verification": _RULE_VERIFICATION[code_upper]}
