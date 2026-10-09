"""Ingesting a published statute and turning it into a rule pack.

Split out of `api/onezero.py`. This is the pull -> extract -> compare -> confirm
-> log lifecycle over a jurisdiction's own published memo. It PROPOSES a
ruleset; a human applies it, and the change is logged against the tax year it
touches [ADR-005]. Nothing here computes a credit.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["rule ingestion"])


@router.get("/rules/ingested/{state}")
def ingested_rules(state: str, tax_year: int | None = None) -> dict[str, Any]:
    """[A5 / GOV-01] The agent-ingested, cited GA rule config + provenance.

    Returns the config the RulesIngestionAgent produced (retrieved from GA
    DCA/DOR/statute via Web IQ) plus a flat provenance table so the Rule
    Library / Eligibility Validation UI can show where every number came from.
    Only GA is in scope (GT-1); other states 404.
    """
    from tools.rules_ingestion import load_ingested_config, provenance_report, has_ingested_config

    st = state.upper()
    if not has_ingested_config(st):
        raise HTTPException(status_code=404, detail=f"No ingested rule config for {st} (GA only in this pass).")
    cfg = load_ingested_config(st)
    return {
        "state": st,
        "program": cfg.get("program"),
        "credit_name": cfg.get("credit_name"),
        "ingestion": cfg.get("ingestion"),
        "config": cfg,
        "provenance": provenance_report(st, tax_year=tax_year),
        "source": "AI-01/A5 RulesIngestionAgent — Web IQ retrieval, per-value citations (GOV-01).",
    }


@router.get("/rules/ingested/{state}/refresh")
def refresh_ingested_rules(state: str, live: bool = False) -> dict[str, Any]:
    """[AI-03 / ARCH-03] Re-run the Web IQ ingestion for a state.

    `live=false` (default) returns the captured cited snapshot deterministically.
    `live=true` probes each trusted source URL and reports reachability + drift
    so the legislative monitor can alert. GA only.
    """
    from tools.rules_ingestion import ingest_ga_jtc, ingest_tn_jtc

    st = state.upper()
    if st == "GA":
        result = ingest_ga_jtc(live=live)
    elif st == "TN":
        result = ingest_tn_jtc(live=live)
    else:
        raise HTTPException(status_code=404, detail=f"Live refresh is available for GA and TN in this pass (requested {st}).")
    return {
        "state": st,
        "mode": result["mode"],
        "sources": result["sources"],
        "parameter_count": len(result["config"].get("parameters", {})),
        "source": "AI-03 LegislativeMonitorAgent — source reachability + drift.",
    }


class ApplyRulesetRequest(BaseModel):
    """[CALC-11 / GOV-01] Confirm + apply a year's ingested rulebook."""
    tax_year: int
    confirmed_by: str = "Tax practitioner"
    note: str | None = None


@router.get("/rules/ingested/{state}/proposals")
def ingestion_proposals(state: str, tax_year: int = 2025) -> dict[str, Any]:
    """[A5 / CALC-11] Pull the year's canonical DCA memo via Web IQ, extract the
    tier schedule + county designations, and COMPARE against the existing
    rulebook. Read-only — returns the diff (tier changes + county tier moves +
    the MeridianCore worksites affected). Does not write anything.
    """
    from tools.rules_ingestion import build_proposals, has_ingested_config

    st = state.upper()
    if st != "GA":
        raise HTTPException(status_code=404, detail=f"Rulebook proposals are GA-only in this pass (requested {st}).")
    return build_proposals(st, tax_year)


@router.post("/rules/ingested/{state}/apply")
def apply_ingested_ruleset(state: str, payload: ApplyRulesetRequest) -> dict[str, Any]:
    """[CALC-11 / GOV-01 / ARCH-02] Confirm + OVERWRITE the year's rulebook from
    the canonical source, logging every change. Date-sensitive: only
    `tax_year` is written; prior years stay frozen.
    """
    from tools.rules_ingestion import apply_ruleset, has_ingested_config
    from tools import webiq

    st = state.upper()
    if st != "GA":
        raise HTTPException(status_code=404, detail=f"Rulebook apply is GA-only in this pass (requested {st}).")
    if not webiq.is_configured():
        raise HTTPException(status_code=503, detail="Web IQ not configured (set WEBIQ_API_KEY) — cannot retrieve the canonical source to apply.")
    try:
        return apply_ruleset(st, payload.tax_year, confirmed_by=payload.confirmed_by, note=payload.note)
    except webiq.WebIQError as e:
        raise HTTPException(status_code=502, detail=f"Web IQ retrieval failed: {e}")


@router.get("/rules/ingested/{state}/changelog")
def ingestion_changelog(state: str) -> dict[str, Any]:
    """[GOV-01] Append-only audit log of applied rulebook changes + which
    dated rulebooks are in force."""
    from tools.rules_ingestion import get_changelog, applied_years, has_ingested_config

    st = state.upper()
    if not has_ingested_config(st):
        raise HTTPException(status_code=404, detail=f"No ingested rule config for {st} (GA only in this pass).")
    return {
        "state": st,
        "applied_years": applied_years(st),
        "changelog": get_changelog(st),
    }
