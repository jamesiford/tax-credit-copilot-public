"""Rules-ingestion tool — the source of the config the calc engine consumes.

Spec: Part A/A5 + Part D + CALC-11 + GOV-01. The guardrail is explicit — GA
Jobs Tax Credit thresholds/rules must **not** be hand-entered into the engine.
They belong in a config the RulesIngestionAgent produces from trusted primary
sources (Georgia DCA / GA DOR / O.C.G.A. § 48-7-40), serialised **with per-value
provenance**, into `data/rules_ingested/<program>.json`. The engine reads that
cited config; the briefing figures are only a sanity check.

RETRIEVAL — now wired to **Microsoft Web IQ** (`tools/webiq.py`, REST v3):

    1. Endpoint + auth: DONE — Web IQ base `https://api.microsoft.ai/v3`,
       `x-apikey` header. The key is read from the env (`WEBIQ_API_KEY`); it is
       never hardcoded (see `backend/.env.example`).
    2. Confirmed authoritative GA source: PENDING — the partner to post the GA DCA
       program link (traceability-matrix ACT-05 / OQ-04). Until then the seeded
       source URLs in the captured config are used, and `search_ga_source()`
       can *discover* the DCA page via Web IQ (`site:dca.ga.gov`).

The two paths:

* ``ingest_ga_jtc(live=False)`` (default; tests + demo) returns the captured
  cited snapshot verbatim — deterministic and reconcilable (POC-02). The values
  in that snapshot were assembled by hand from public GA references as a
  stand-in; each still carries its source URL + `_prototype_verify` so nothing
  is presented as verified.
* ``ingest_ga_jtc(live=True)`` — when a Web IQ key is configured — **actually
  retrieves** each source URL via Web IQ ``browse`` (real grounding + crawl
  timestamps) and marks the source ``verified``. It does NOT auto-overwrite a
  threshold value: extracting and re-serialising numbers stays behind the human
  checkpoint (GOV-01 / AI-02). With no key, it degrades to a reachability probe
  and reports ``web_iq_status = NEEDS_KEY``.

`load_ingested_config` / `ingested_one_zero` / `provenance_report` are real and
drive the live GA eligibility flow off the cited config.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from domain.calculation.trail import current_recorder

_INGESTED_DIR = Path(__file__).resolve().parent.parent / "data" / "rules_ingested"

# Program code -> ingested-config filename. GA is the client-facing pass (GT-1);
# TN carries a statute-grounded cited config (T.C.A. § 67-4-2109, verified
# 2026-07-15) whose floors match the static pack so it changes no computed value.
_PROGRAM_FILE: dict[str, str] = {
    "GA_JTC": "ga_jtc.json",
    "GA": "ga_jtc.json",
    "TN_JTC": "tn_jtc.json",
    "TN": "tn_jtc.json",
}


# ---------------------------------------------------------------------------
# Config access
# ---------------------------------------------------------------------------


def _config_path(program_or_state: str) -> Path | None:
    fname = _PROGRAM_FILE.get(program_or_state.upper())
    if not fname:
        return None
    path = _INGESTED_DIR / fname
    return path if path.exists() else None


def load_ingested_config(program_or_state: str) -> dict[str, Any] | None:
    """Return the cited config for a program/state, or None if not ingested.

    Only GA JTC is ingested in this prototype pass (GT-1). Everything else
    returns None so callers fall back to the static rule-pack JSON.
    """
    path = _config_path(program_or_state)
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def has_ingested_config(program_or_state: str) -> bool:
    return _config_path(program_or_state) is not None


# ---------------------------------------------------------------------------
# Engine feed (CALC-11): the cited config drives the eligibility floors
# ---------------------------------------------------------------------------


def ingested_one_zero(program_or_state: str, tax_year: int | None = None) -> dict[str, Any] | None:
    """Resolve the cited config into the flat ``one_zero`` shape the engine reads.

    Returns a dict with the same keys `credit_math.load_pack_one_zero` expects
    (``min_weekly_hours``, ``min_weekly_wages``, ``wage_basis``,
    ``measuring_date``, ``included_pay_codes``, ``excluded_pay_codes``) plus a
    ``provenance`` map so the eligibility trail can cite each floor. Year-specific
    overrides in ``thresholds_by_year`` win over the base parameter values.
    """
    cfg = load_ingested_config(program_or_state)
    if cfg is None:
        return None
    params = cfg.get("parameters", {})

    def _val(name: str, default: Any = None) -> Any:
        node = params.get(name)
        return node.get("value") if isinstance(node, dict) else default

    min_hours = float(_val("min_weekly_hours", 0.0) or 0.0)
    min_wages = float(_val("min_weekly_wages", 0.0) or 0.0)

    # [CALC-03] Year-specific override (e.g. GA 2025 wage floor).
    if tax_year is not None:
        yblock = (cfg.get("thresholds_by_year") or {}).get(str(tax_year))
        if isinstance(yblock, dict) and "min_weekly_wages" in yblock:
            min_wages = float(yblock["min_weekly_wages"])
        if isinstance(yblock, dict) and "min_weekly_hours" in yblock:
            min_hours = float(yblock["min_weekly_hours"])

    wage_node = params.get("wage_basis", {}) if isinstance(params.get("wage_basis"), dict) else {}
    included = wage_node.get("included_pay_codes")
    excluded = wage_node.get("excluded_pay_codes")

    return {
        "min_weekly_hours": min_hours,
        "min_weekly_wages": min_wages,
        "wage_basis": _val("wage_basis", "all_remuneration"),
        "measuring_date": _val("measuring_date", "last_day"),
        "included_pay_codes": included,
        "excluded_pay_codes": excluded,
        "source": "rules_ingested",
        "provenance": provenance_report(program_or_state, tax_year=tax_year),
    }


# ---------------------------------------------------------------------------
# Provenance (GOV-01): flat per-value citation list for UI + audit
# ---------------------------------------------------------------------------


def provenance_report(program_or_state: str, tax_year: int | None = None) -> list[dict[str, Any]]:
    """Flatten cited config into URL- or artifact-hash-backed provenance rows.

    The Rule Library can render where every value came from without requiring a
    public URL for governed local stakeholder evidence.
    """
    cfg = load_ingested_config(program_or_state)
    if cfg is None:
        return []
    rows: list[dict[str, Any]] = []
    for name, node in (cfg.get("parameters") or {}).items():
        if not isinstance(node, dict):
            continue
        src = node.get("source", {})
        rows.append(
            {
                "parameter": name,
                "value": node.get("value"),
                "authority": src.get("authority"),
                "title": src.get("title"),
                "url": src.get("url"),
                "artifact_sha256": src.get("artifact_sha256"),
                "retrieved_at": src.get("retrieved_at"),
                "confidence": node.get("confidence"),
                "verify": bool(node.get("_prototype_verify", False)),
                "disc_ref": node.get("_disc_ref"),
            }
        )
    if tax_year is not None:
        yblock = (cfg.get("thresholds_by_year") or {}).get(str(tax_year))
        if isinstance(yblock, dict):
            src = yblock.get("source", {})
            rows.append(
                {
                    "parameter": f"min_weekly_wages@{tax_year}",
                    "value": yblock.get("min_weekly_wages"),
                    "authority": src.get("authority"),
                    "title": src.get("title"),
                    "url": src.get("url"),
                    "artifact_sha256": src.get("artifact_sha256"),
                    "retrieved_at": src.get("retrieved_at"),
                    "confidence": yblock.get("confidence"),
                    "verify": bool(yblock.get("_prototype_verify", False)),
                    "disc_ref": yblock.get("_disc_ref"),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Retrieval (A5 / AI-03): Web IQ ingest + drift detection
# ---------------------------------------------------------------------------


def _source_urls(cfg: dict[str, Any]) -> list[str]:
    urls: set[str] = set()
    for node in (cfg.get("parameters") or {}).values():
        if isinstance(node, dict):
            url = (node.get("source") or {}).get("url")
            if url:
                urls.add(url)
    return sorted(urls)


def _probe(url: str, timeout: float = 6.0) -> bool:
    """Best-effort reachability probe of a source URL (Web IQ retrieval step)."""
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "TaxCreditCopilot/rules-ingestion"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed trusted GA URLs
            return 200 <= getattr(resp, "status", 200) < 400
    except (URLError, ValueError, OSError):
        return False


def search_ga_source(query: str = "Georgia Jobs Tax Credit tier county wage threshold", *, site: str = "dca.ga.gov") -> list[dict[str, Any]]:
    """Discover the authoritative GA source via Web IQ web search (scoped to a site).

    Addresses the open item "which GA site do we pull the rules from?" — Web IQ
    finds and returns the DCA page(s) with query-contextual passages. Requires a
    Web IQ credential; returns [] with a note when unconfigured.
    """
    from . import webiq
    if not webiq.is_configured():
        return []
    try:
        return webiq.search_web(query, site=site, max_results=5)
    except webiq.WebIQError:
        return []


_PROGRAM_MISSING = {
    "GA_JTC": "data/rules_ingested/ga_jtc.json",
    "TN_JTC": "data/rules_ingested/tn_jtc.json",
}


def _ingest_program(program_code: str, *, live: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    """Shared ingestion spine — produce a program's cited config with source
    reachability/drift.

    ``live=False`` (default) returns the captured snapshot verbatim —
    deterministic and reconcilable; this is what tests + the demo use.
    ``live=True`` retrieves each source URL through **Microsoft Web IQ**
    (`webiq.browse`) when a key is configured: it captures the real page
    grounding (content length), the title, and the crawl timestamp, and marks
    the source ``verified``. It NEVER auto-overwrites a threshold value —
    proposing new numbers stays behind the human checkpoint (GOV-01). With no
    Web IQ key it degrades to a plain HTTP reachability probe and reports
    ``web_iq_status = NEEDS_KEY``.
    """
    from . import webiq

    cfg = load_ingested_config(program_code)
    if cfg is None:
        raise FileNotFoundError(f"{program_code} ingested config missing: {_PROGRAM_MISSING.get(program_code, 'data/rules_ingested/')}")

    web_iq_meta = (cfg.get("ingestion", {}) or {}).get("web_iq", {})
    status = webiq.runtime_status() if live else "captured"
    result: dict[str, Any] = {
        "program": program_code,
        "mode": "live" if live else "captured",
        "web_iq_status": status,
        "web_iq_needs": web_iq_meta.get("needs", []),
        "config": cfg,
        "sources": [],
    }

    urls = _source_urls(cfg)
    today = date.today().isoformat()
    for url in urls:
        entry: dict[str, Any] = {"url": url}
        if not live:
            entry.update({"reachable": None, "verified": None, "last_checked": web_iq_meta.get("_note") and cfg.get("ingestion", {}).get("captured_at")})
        elif webiq.is_configured():
            # Real Web IQ retrieval — capture grounding + provenance.
            try:
                page = webiq.browse(url, content_format="markdown", max_length=8000)
                entry.update({
                    "retrieved_via": "web_iq_browse",
                    "verified": True,
                    "title": page.get("title"),
                    "content_chars": len(page.get("content") or ""),
                    "crawled_at": page.get("crawledAt"),
                    "last_checked": today,
                })
            except webiq.WebIQError as e:
                entry.update({"retrieved_via": "web_iq_browse", "verified": False, "error": str(e), "last_checked": today})
        else:
            # No key — reachability probe fallback so the seam still reports something.
            entry.update({"retrieved_via": "http_head_probe", "reachable": _probe(url, timeout=6.0), "verified": None, "last_checked": today})
        result["sources"].append(entry)

    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step=f"Ingest {program_code} rules (Web IQ retrieval)",
            inputs={"program": program_code, "mode": result["mode"], "web_iq": status, "source_count": len(urls)},
            formula="webiq.browse(source_url) -> grounding + provenance; values held for human checkpoint (GOV-01)",
            output={"parameters": len(cfg.get("parameters", {})), "sources": len(urls), "web_iq": status},
            citation="; ".join(urls),
        )
    return result


def ingest_ga_jtc(*, live: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    """Produce the GA JTC cited config (Web IQ retrieval over the DCA memo +
    statute sources). See ``_ingest_program`` for the mechanics — ``live=False``
    returns the captured snapshot; ``live=True`` browses each source via Web IQ
    (verified + crawl timestamp) and never auto-overwrites a threshold (GOV-01).
    """
    return _ingest_program("GA_JTC", live=live, timeout=timeout)


def ingest_tn_jtc(*, live: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    """Produce the TN JTC cited config with source reachability/drift.

    Same contract as ``ingest_ga_jtc`` over the Tennessee sources (T.C.A.
    § 67-4-2109 statute + TNECD). ``live=True`` browses each source via Web IQ
    for reachability + crawl timestamps so the LegislativeMonitorAgent can
    alert on drift; it never overwrites a value (GOV-01). NOTE: the TN cited
    config has no annual-memo extraction, so this is reachability/drift
    monitoring only — the rulebook proposals/apply flow stays GA-only.
    """
    return _ingest_program("TN_JTC", live=live, timeout=timeout)


# ===========================================================================
# Date-sensitive rulebook ingestion (extract -> compare -> confirm -> apply)
# ---------------------------------------------------------------------------
# The DCA "Job Tax Credit Annual Ranking Memo" is published per year and is the
# canonical source for (a) the 4-tier credit schedule (job minimum + $/job) and
# (b) all 159 county -> tier designations. We browse it via Web IQ, EXTRACT the
# values deterministically, COMPARE against our existing ruleset, and — on human
# confirmation — OVERWRITE the year's rulebook while LOGGING every change.
#
# Rulebooks are DATE-SENSITIVE: each tax year is its own frozen ruleset. Applying
# 2026 never mutates 2024/2025. Storage here is in-memory (prototype pattern —
# resets on restart, like _MANUAL_CLAIMS); production persists to Fabric with
# SCD Type 2 history (ARCH-02).
# ===========================================================================

# key f"{program}:{year}" -> {"tier_schedule": {...}, "county_tiers": {...}, meta}
_APPLIED_RULESETS: dict[str, dict[str, Any]] = {}
# append-only audit log of every applied change (GOV-01).
_CHANGELOG: list[dict[str, Any]] = []

# Tier N counties necessitate (at least|only) J net new jobs ... credit of $A per net new job
_TIER_RE = re.compile(
    r"Tier\s*([1-4])\s*counties?\s+necessitate\s+(?:at least|only)?\s*(\d+)\s*net\s*new\s*jobs?"
    r"[^$]*?credit of \$([\d,]+)\s*per\s*net\s*new\s*job",
    re.IGNORECASE,
)


def _memo_url_for(tax_year: int) -> str:
    """Canonical DCA Job Tax Credit Annual Ranking Memo URL for a tax year."""
    return f"https://dca.georgia.gov/document/document/{tax_year}-job-tax-credit-annual-ranking-memo/download"


def extract_tier_schedule(text: str) -> dict[str, dict[str, Any]]:
    """Deterministically extract the 4-tier credit schedule from memo text.

    Returns ``{"1": {"min_new_jobs": 2, "per_job_usd": 3500, "evidence": "..."}, ...}``.
    """
    out: dict[str, dict[str, Any]] = {}
    for m in _TIER_RE.finditer(text):
        tier = m.group(1)
        out[tier] = {
            "min_new_jobs": int(m.group(2)),
            "per_job_usd": int(m.group(3).replace(",", "")),
            "evidence": " ".join(m.group(0).split())[:160],
        }
    return out


def extract_county_tiers(text: str) -> dict[str, int]:
    """Extract the county -> tier map from the memo's ranking table (159 counties)."""
    i = text.find("Job Tax Credit Rankings")
    seg = text[i:i + 6000] if i >= 0 else text
    parts = re.split(r"Tier\s*([1-4])", seg)
    cmap: dict[str, int] = {}
    for k in range(1, len(parts), 2):
        tier = int(parts[k])
        body = parts[k + 1] if k + 1 < len(parts) else ""
        for m in re.finditer(r"\d+\\?\.\s*([A-Z][A-Za-z\. ]+?)\s*(?=\||\d+\\?\.|$)", body):
            name = m.group(1).strip()
            if name and name not in cmap:
                cmap[name] = tier
    return cmap


def retrieve_ruleset(state: str, tax_year: int) -> dict[str, Any]:
    """Pull + extract the canonical ruleset for a year from the DCA memo (Web IQ).

    Raises ``webiq.WebIQError`` when Web IQ is not configured or the source is
    unreachable — callers handle that as ``NEEDS_KEY`` / unavailable.
    """
    from . import webiq

    url = _memo_url_for(tax_year)
    page = webiq.browse(url, content_format="markdown", max_length=16000)
    text = page.get("content") or ""
    return {
        "state": state.upper(),
        "tax_year": tax_year,
        "source_url": url,
        "source_title": page.get("title"),
        "crawled_at": page.get("crawledAt"),
        "retrieved_at": date.today().isoformat(),
        "tier_schedule": extract_tier_schedule(text),
        "county_tiers": extract_county_tiers(text),
        "content_chars": len(text),
    }


def _config_tier1_baseline(state: str) -> dict[str, dict[str, Any]]:
    """The Tier-1 values the engine currently ships (from the ingested config)."""
    cfg = load_ingested_config(state) or {}
    p = cfg.get("parameters", {})
    return {
        "1": {
            "min_new_jobs": (p.get("minimum_new_jobs") or {}).get("value"),
            "per_job_usd": (p.get("amount_per_qualifying_job_usd") or {}).get("value"),
        }
    }


def current_ruleset(state: str, tax_year: int) -> dict[str, Any]:
    """The ruleset currently in force for a year: the applied one if present, else
    the config-shipped Tier-1 baseline (Tiers 2-4 unknown until first ingest)."""
    key = f"GA_JTC:{tax_year}"
    if key in _APPLIED_RULESETS:
        return _APPLIED_RULESETS[key]
    return {
        "state": state.upper(),
        "tax_year": tax_year,
        "source": "config_baseline",
        "tier_schedule": _config_tier1_baseline(state),
        "county_tiers": {},
    }


def _diff_schedule(current: dict, proposed: dict) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tier in sorted(proposed, key=int):
        cur = current.get(tier, {})
        prop = proposed[tier]
        for field in ("min_new_jobs", "per_job_usd"):
            c, p = cur.get(field), prop.get(field)
            rows.append({
                "tier": int(tier),
                "field": field,
                "current": c,
                "proposed": p,
                "changed": c != p,
                "is_new": c is None,
                "evidence": prop.get("evidence"),
            })
    return rows


def _county_moves(prior_counties: dict[str, int], proposed_counties: dict[str, int]) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    if not prior_counties:
        return moves  # baseline establishment — no prior to diff
    for county, tier in sorted(proposed_counties.items()):
        prev = prior_counties.get(county)
        if prev is not None and prev != tier:
            moves.append({"county": county, "from_tier": prev, "to_tier": tier})
    return moves


def _meridiancore_ga_counties() -> dict[str, str]:
    """MeridianCore GA site counties -> site label, so ingestion can flag
    designation changes that actually touch the client's worksites."""
    try:
        from data.sites import get_all_sites
        return {
            (s.get("county") or "").replace(" County", "").strip(): s.get("name") or s.get("site_id")
            for s in get_all_sites()
            if (s.get("state") == "GA") and s.get("county")
        }
    except Exception:  # noqa: BLE001
        return {}


def build_proposals(state: str, tax_year: int) -> dict[str, Any]:
    """Pull the year's memo, extract, and COMPARE against the existing ruleset.

    Returns a diff (tier-schedule changes + county tier moves vs the prior year)
    plus the MeridianCore worksites whose county designation moved. Does NOT
    write anything — that is the ``apply_ruleset`` step. Degrades to a
    ``web_iq_status=NEEDS_KEY`` response (no network) when Web IQ isn't configured.
    """
    from . import webiq

    if not webiq.is_configured():
        return {
            "state": state.upper(),
            "tax_year": tax_year,
            "web_iq_status": "NEEDS_KEY",
            "message": "Web IQ key not configured — set WEBIQ_API_KEY to retrieve the DCA ranking memo.",
            "schedule_diff": [],
            "county_moves": [],
            "meridiancore_impact": [],
        }
    try:
        proposed = retrieve_ruleset(state, tax_year)
    except webiq.WebIQError as e:
        return {
            "state": state.upper(),
            "tax_year": tax_year,
            "web_iq_status": "SOURCE_ERROR",
            "message": f"Could not retrieve the {tax_year} DCA ranking memo: {e}",
            "schedule_diff": [],
            "county_moves": [],
            "meridiancore_impact": [],
        }

    current = current_ruleset(state, tax_year)
    schedule_diff = _diff_schedule(current.get("tier_schedule", {}), proposed["tier_schedule"])

    # County moves are year-over-year: compare to the prior year (applied if we
    # have it, else retrieve it best-effort).
    prior_key = f"GA_JTC:{tax_year - 1}"
    prior_counties: dict[str, int] = {}
    if prior_key in _APPLIED_RULESETS:
        prior_counties = _APPLIED_RULESETS[prior_key].get("county_tiers", {})
    else:
        try:
            prior_counties = retrieve_ruleset(state, tax_year - 1).get("county_tiers", {})
        except webiq.WebIQError:
            prior_counties = {}
    moves = _county_moves(prior_counties, proposed["county_tiers"])

    ga_counties = _meridiancore_ga_counties()
    impact = [
        {**mv, "worksite": ga_counties[mv["county"]]}
        for mv in moves
        if mv["county"] in ga_counties
    ]

    return {
        "state": state.upper(),
        "tax_year": tax_year,
        "web_iq_status": "READY",
        "source_url": proposed["source_url"],
        "source_title": proposed.get("source_title"),
        "retrieved_at": proposed["retrieved_at"],
        "content_chars": proposed["content_chars"],
        "tier_schedule": proposed["tier_schedule"],
        "county_count": len(proposed["county_tiers"]),
        "schedule_diff": schedule_diff,
        "schedule_changes": sum(1 for r in schedule_diff if r["changed"] and not r["is_new"]),
        "schedule_new": sum(1 for r in schedule_diff if r["is_new"]),
        "county_moves": moves,
        "county_move_count": len(moves),
        "meridiancore_impact": impact,
        "compared_to_year": tax_year - 1 if prior_counties else None,
    }


def apply_ruleset(state: str, tax_year: int, *, confirmed_by: str, note: str | None = None) -> dict[str, Any]:
    """Re-pull the canonical source, then OVERWRITE the year's rulebook and LOG
    every change. Date-sensitive: only ``tax_year`` is written; prior years are
    frozen. The client confirms; it does not supply values — the applied values
    are exactly what was retrieved from the DCA memo (audit integrity).
    """
    proposed = retrieve_ruleset(state, tax_year)  # raises WebIQError if unavailable
    current = current_ruleset(state, tax_year)
    schedule_diff = _diff_schedule(current.get("tier_schedule", {}), proposed["tier_schedule"])

    now = datetime.now(timezone.utc).isoformat()
    key = f"GA_JTC:{tax_year}"
    entries: list[dict[str, Any]] = []
    for row in schedule_diff:
        if row["changed"]:
            entry = {
                "timestamp": now,
                "program": "GA_JTC",
                "state": state.upper(),
                "tax_year": tax_year,
                "parameter": f"tier{row['tier']}.{row['field']}",
                "old_value": row["current"],
                "new_value": row["proposed"],
                "action": "created" if row["is_new"] else "updated",
                "source_url": proposed["source_url"],
                "evidence": row["evidence"],
                "confirmed_by": confirmed_by,
                "note": note,
            }
            _CHANGELOG.append(entry)
            entries.append(entry)

    _APPLIED_RULESETS[key] = {
        "state": state.upper(),
        "tax_year": tax_year,
        "source": "web_iq_dca_memo",
        "source_url": proposed["source_url"],
        "retrieved_at": proposed["retrieved_at"],
        "applied_at": now,
        "confirmed_by": confirmed_by,
        "tier_schedule": proposed["tier_schedule"],
        "county_tiers": proposed["county_tiers"],
    }

    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step=f"Apply {tax_year} GA JTC rulebook from DCA memo",
            inputs={"tax_year": tax_year, "confirmed_by": confirmed_by, "source": proposed["source_url"]},
            formula="browse(memo) -> extract tier schedule + county tiers -> overwrite year rulebook + append changelog",
            output={"changes": len(entries), "counties": len(proposed["county_tiers"])},
            citation=proposed["source_url"],
        )

    return {
        "state": state.upper(),
        "tax_year": tax_year,
        "applied_at": now,
        "confirmed_by": confirmed_by,
        "changes_logged": len(entries),
        "changelog_entries": entries,
        "tier_schedule": proposed["tier_schedule"],
        "county_count": len(proposed["county_tiers"]),
    }


def get_changelog(state: str | None = None) -> list[dict[str, Any]]:
    """Append-only audit log of applied rulebook changes (most recent first)."""
    rows = _CHANGELOG
    if state:
        rows = [r for r in rows if r.get("state") == state.upper()]
    return list(reversed(rows))


def applied_years(state: str = "GA") -> list[dict[str, Any]]:
    """Which tax-year rulebooks have been applied (date-sensitive view)."""
    out: list[dict[str, Any]] = []
    for key, rs in sorted(_APPLIED_RULESETS.items()):
        if not key.startswith("GA_JTC:"):
            continue
        out.append({
            "tax_year": rs["tax_year"],
            "applied_at": rs.get("applied_at"),
            "confirmed_by": rs.get("confirmed_by"),
            "source_url": rs.get("source_url"),
            "tier_count": len(rs.get("tier_schedule", {})),
            "county_count": len(rs.get("county_tiers", {})),
        })
    return out

