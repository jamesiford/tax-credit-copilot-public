"""Credit-math tools: apply a JSON rule pack to a statutory headcount figure."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from domain.calculation.floors import StatutoryFloors, program_name
from domain.calculation.trail import current_recorder

_RULES = Path(__file__).resolve().parent.parent / "rules"

# Two-letter state -> rule pack filename. Adding a new state credit is a JSON
# file plus one line here. States NOT in this map (e.g. TX) flow through
# apply_one_zero_state_credit() and get a structured "no_state_pack" response.
STATE_TO_PACK: dict[str, str] = {
    "GA": "ga_jtc.json",
    "NY": "ny_excelsior.json",
    "SC": "sc_jtc.json",
    # Phase A expansion states
    "NC": "nc_jtec.json",
    "TN": "tn_jtc.json",
    "FL": "fl_qti.json",
    "OH": "oh_jctc.json",
    "CO": "co_ez.json",
    "VA": "va_mbjf.json",
}

# Program code (as it appears in a pack's `credit.code`) -> pack filename. An
# assumption set names the programme it measures by code, not by state, because
# a state can run several credits and a credit can outlive its state's tier map.
PROGRAM_CODE_TO_PACK: dict[str, str] = {
    "GA_JTC": "ga_jtc.json",
    "NY_EXCELSIOR": "ny_excelsior.json",
    "SC_JTC": "sc_jtc.json",
    "NC_JTEC": "nc_jtec.json",
    "TN_JTC": "tn_jtc.json",
    "FL_QTI": "fl_qti.json",
    "OH_JCTC": "oh_jctc.json",
    "CO_EZ": "co_ez.json",
    "VA_MBJF": "va_mbjf.json",
}


def _load_pack(filename: str) -> dict[str, Any]:
    path = _RULES / filename
    if not path.exists():
        raise FileNotFoundError(f"rule pack not found: {filename}")
    return json.loads(path.read_text(encoding="utf-8"))


def _program_name(pack_file: str) -> str:
    """`ga_jtc.json` -> `ga_jtc`. The directory name for its year packs."""
    return program_name(pack_file)


def is_year_scoped(pack_file: str) -> bool:
    """Has this program been migrated to year-scoped packs? [ADR-005]

    Migration is per-program: a program with a `rules/<program>/` directory is
    year-scoped and resolution is strict. One without is still flat, and resolves
    the legacy way.
    """
    return (_RULES / _program_name(pack_file)).is_dir()


def load_year_pack(pack_file: str, tax_year: int | None) -> tuple[dict[str, Any], bool]:
    """Resolve a rule pack for a tax year. Returns `(pack, year_resolved)`.

    [ADR-005] Once a program is year-scoped, resolution **fails loudly**: a
    missing year raises rather than falling back to a neighbouring year or to the
    flat default. A missing ruleset is a real gap in statutory coverage, and the
    honest response is to say so rather than to produce a confident number under
    the wrong year's rules.

    Programs not yet migrated resolve from the flat pack and return
    `year_resolved=False`, so a caller can tell an authored year from an
    inherited one. That flag is the migration signal — when every program is
    year-scoped it is always True and this branch goes.
    """
    program = _program_name(pack_file)

    if is_year_scoped(pack_file):
        authored = sorted(int(p.stem) for p in (_RULES / program).glob("*.json") if p.stem.isdigit())
        if tax_year is None:
            # Describing a program ("what is GA JTC?") is a legitimate call and
            # should not raise. Return the most recent authored year with
            # year_resolved=False — any CALCULATION path must require True,
            # because a credit cannot be computed without knowing which year's
            # statute applies.
            if not authored:
                return _load_pack(pack_file), False
            latest = _RULES / program / f"{authored[-1]}.json"
            return json.loads(latest.read_text(encoding="utf-8")), False
        path = _RULES / program / f"{tax_year}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"no rule pack for {program} tax year {tax_year}. "
                f"Authored years: {', '.join(str(y) for y in authored) or 'none'}. "
                f"ADR-005: statute is not inherited across years — author the "
                f"year or decline to calculate it."
            )
        return json.loads(path.read_text(encoding="utf-8")), True

    return _load_pack(pack_file), False


#: Re-exported so existing callers keep importing it from here. The definition
#: lives in the domain because the pure calculation types its arguments with it.
__all__ = [*globals().get("__all__", []), "StatutoryFloors"]


def authored_years(pack_file: str) -> list[int]:
    """Which tax years this program has an authored rule pack for.

    The single answer to "can this program be priced, and for when?". Both the
    scope selector and the assessment path read it, so they cannot disagree
    about whether a program is calculable — an inconsistency there produces a
    figure on one screen that another screen says is impossible.

    Empty means describable but **not calculable**: `load_pack_one_zero` still
    returns a flat pack for an unmigrated program, so a caller that skips this
    check will happily compute a number under no particular year's statute.
    """
    program = _program_name(pack_file)
    directory = _RULES / program
    if not directory.is_dir():
        return []
    return sorted(int(p.stem) for p in directory.glob("*.json") if p.stem.isdigit())


def resolve_tax_year_convention(program_code: str, tax_year: int | None = None) -> dict[str, Any]:
    """How a programme labels a tax year: by the year it begins, or the year it ends.

    A statutory fact, so it lives in the rule pack beside the wage floor rather
    than in a client setting or a helper function. Authorities differ, and the
    choice selects which year's statute applies [ADR-005].

    Falls back to `begins` when a pack has not authored one, flagged `assumed`.
    That default matches Georgia's regulation and the certified reference run, and
    it is what every current client already resolves to — but a caller that
    cares must check the flag rather than trust the value.
    """
    try:
        pack_file = PROGRAM_CODE_TO_PACK[program_code]
    except KeyError as exc:
        raise ValueError(
            f"unknown program code {program_code!r}. "
            f"Known: {', '.join(sorted(PROGRAM_CODE_TO_PACK))}."
        ) from exc

    try:
        pack, _ = load_year_pack(pack_file, tax_year)
    except (FileNotFoundError, ValueError):
        pack = _load_pack(pack_file)

    block = dict(pack.get("tax_year_convention") or {})
    label = block.get("label")
    if label not in ("begins", "ends"):
        return {
            "label": "begins",
            "assumed": True,
            "unconfirmed": True,
            "regulation": None,
            "note": (
                f"{program_code} has not authored a tax-year labelling convention. "
                f"Defaulting to 'begins', which matches Georgia's regulation and every "
                f"client currently on file. Confirm before pricing a non-calendar filer."
            ),
        }

    return {
        "label": label,
        "assumed": False,
        # Read from the regulation; not yet confirmed by the partner.
        "unconfirmed": bool(block.get("_prototype_verify")),
        "regulation": block.get("regulation"),
        "note": block.get("_note", ""),
    }


def resolve_statutory_floors(program_code: str, tax_year: int) -> StatutoryFloors:
    """Resolve one programme-year's statutory floors from its rule pack.

    The single lookup for "what did this programme require in this year?". The
    tax year is mandatory: a floor without a year is not a statutory fact, and
    every caller here is about to compute a number that lands on a return.
    """
    if tax_year is None:
        raise ValueError(
            f"cannot resolve statutory floors for {program_code} without a tax year. "
            f"ADR-005: the floor is a property of the year."
        )
    try:
        pack_file = PROGRAM_CODE_TO_PACK[program_code]
    except KeyError as exc:
        raise ValueError(
            f"unknown program code {program_code!r}. "
            f"Known: {', '.join(sorted(PROGRAM_CODE_TO_PACK))}."
        ) from exc

    pack, year_resolved = load_year_pack(pack_file, tax_year)
    if not year_resolved:
        raise ValueError(
            f"{program_code} is not year-scoped, so tax year {tax_year} cannot be "
            f"resolved. Materialise its year packs first: "
            f"python -m data.rules.materialise_years {_program_name(pack_file)} "
            f"--years {tax_year}"
        )

    one_zero = pack.get("one_zero") or {}
    for key in ("min_weekly_hours", "min_weekly_wages"):
        if one_zero.get(key) is None:
            raise ValueError(
                f"rule pack for {program_code} tax year {tax_year} has no {key}."
            )

    return StatutoryFloors(
        program_code=program_code,
        tax_year=tax_year,
        min_weekly_hours=one_zero["min_weekly_hours"],
        min_weekly_wages=one_zero["min_weekly_wages"],
        basis=dict(one_zero.get("wage_floor_basis") or {}),
        provenance=dict(pack.get("_year_provenance") or {}),
        pack_file=pack_file,
    )


def _avg_state_wage(state: str) -> float:
    from .payroll import _load_rows
    rows = [r for r in _load_rows() if r["location_state"] == state]
    if not rows:
        return 0.0
    return sum(r["annual_wage"] for r in rows) / len(rows)


def _no_state_pack_result(state: str) -> dict[str, Any]:
    """Structured response for a state with no rule pack (e.g. TX).

    Returns `no_state_pack=True` with a user-facing message so callers surface
    it honestly instead of silently running the wrong math, and records the
    look-up step into the active calculation trail.
    """
    state_u = state.upper()
    result = {
        "state": state_u,
        "no_state_pack": True,
        "credit_code": None,
        "credit_name": None,
        "jurisdiction": state_u,
        "citation": None,
        "threshold": None,
        "qualifying_jobs": 0,
        "amount_per_job_usd": 0,
        "annual_credit_usd": 0,
        "benefit_period_years": 0,
        "lifetime_credit_usd": 0,
        "message": (
            f"No state-level rule pack for {state_u} in our library "
            f"(have: {', '.join(sorted(STATE_TO_PACK.keys()))}). "
            "Federal credits like WOTC may still apply — try the portfolio or discovery question."
        ),
    }
    recorder = current_recorder()
    if recorder is not None:
        if not recorder.title or recorder.title == "Pending":
            recorder.title = f"{state_u}: no state pack"
        recorder.record(
            step=f"Look up state rule pack for {state_u}",
            inputs={"state": state_u, "library": sorted(STATE_TO_PACK.keys())},
            formula="STATE_TO_PACK[state]",
            output={"pack": None, "fallback": "federal only"},
            citation="backend/rules/",
        )
    return result


# ---------------------------------------------------------------------------
# One/Zero Base Calculation — shared core (Session A of the roadmap)
# ---------------------------------------------------------------------------


def load_pack_one_zero(state_or_code: str, tax_year: int | None = None):
    """Build a `OneZeroPack` from a state code or credit code.

    `state_or_code` accepts either a two-letter state code (e.g. 'GA') or a
    credit code that matches a rule pack's `credit.code` (e.g. 'GA_JTC').
    Returns None if no pack matches OR if the matched pack has no `one_zero`
    block.

    [H1] CALC-03 — when the pack carries a `thresholds_by_year` map and a
    `tax_year` is supplied, that year's floors override the flat defaults.
    The flat `min_weekly_hours` / `min_weekly_wages` fields remain the
    default-year fallback (and satisfy the rule-pack schema tests).
    """
    from domain.calculation.onezero import OneZeroMethodology, OneZeroPack  # local import: avoid load-time cycle

    s = state_or_code.upper()
    pack_file = STATE_TO_PACK.get(s)
    if pack_file is None:
        # Try matching by credit code across all packs.
        for fname in STATE_TO_PACK.values():
            pack = _load_pack(fname)
            if pack.get("credit", {}).get("code") == s:
                pack_file = fname
                break
        else:
            # Also try federal packs (federal_wotc_lite.json etc., not in STATE_TO_PACK).
            for path in _RULES.glob("*.json"):
                pack = _load_pack(path.name)
                if pack.get("credit", {}).get("code") == s:
                    pack_file = path.name
                    break
    if pack_file is None:
        return None

    # [ADR-005] Year-scoped programs resolve to a materialised (program, year)
    # pack. Programs not yet migrated fall back to the flat pack, and
    # `thresholds_by_year` below still applies to those.
    pack, year_resolved = load_year_pack(pack_file, tax_year)
    oz = pack.get("one_zero")
    if not oz:
        return None

    resolved = dict(oz)
    if not year_resolved:
        # [H1] Legacy path: overlay year-specific thresholds onto flat defaults.
        # A materialised pack has these baked in already, and its
        # `thresholds_by_year` was stripped at authoring time.
        tby = oz.get("thresholds_by_year")
        if tby and tax_year is not None:
            year_block = tby.get(str(tax_year))
            if year_block:
                resolved.update(year_block)

    pt_band = resolved.get("pt_band_hours")
    pt_band_tuple = (float(pt_band[0]), float(pt_band[1])) if pt_band else None
    pt_weight = resolved.get("pt_weight")

    # [L5] CALC-11 — pay-code inclusion/suppression for the weekly-wage test.
    pcp = oz.get("pay_code_policy") or {}
    inc = pcp.get("included_pay_codes")
    exc = pcp.get("excluded_pay_codes")

    # [A5 / CALC-11 / GT-5] Prefer the agent-INGESTED cited config over the
    # static JSON pack. The RulesIngestionAgent retrieves GA JTC floors from
    # trusted primary sources (GA DCA/DOR/statute) via Web IQ and serialises
    # them WITH provenance; when that config exists it drives the eligibility
    # floors so no threshold is hand-entered into the engine. Falls back to the
    # static pack values above when no ingested config is present.
    try:
        from .rules_ingestion import ingested_one_zero  # local import: optional dependency
        ing = ingested_one_zero(s, tax_year=tax_year)
    except Exception:  # noqa: BLE001 — ingestion must never break the calc
        ing = None
    if ing:
        # [ADR-005] A year-resolved pack is AUTHORED STATUTE for that specific
        # year. The ingested config is a general retrieval that is not
        # year-scoped — it returns the same floor for 2021 and 2025 — so letting
        # it win would silently erase the year packs and reintroduce exactly the
        # failure ADR-005 exists to prevent: 2026 rules applied to 2021 payroll.
        #
        # So: ingestion may FILL values a pack lacks, never OVERRIDE a
        # year-resolved one.
        if not year_resolved:
            resolved["min_weekly_hours"] = ing["min_weekly_hours"]
            resolved["min_weekly_wages"] = ing["min_weekly_wages"]
        resolved["wage_basis"] = ing.get("wage_basis", resolved.get("wage_basis"))
        resolved["measuring_date"] = ing.get("measuring_date", resolved.get("measuring_date", "last_day"))
        if ing.get("included_pay_codes"):
            inc = ing["included_pay_codes"]
        if ing.get("excluded_pay_codes"):
            exc = ing["excluded_pay_codes"]

    return OneZeroPack(
        min_weekly_hours=float(resolved["min_weekly_hours"]),
        min_weekly_wages=float(resolved.get("min_weekly_wages", 0.0)),
        wage_basis=str(resolved.get("wage_basis", oz.get("wage_basis", "regular"))),
        geographic_granularity=str(oz.get("geographic_granularity", "unit")),
        pt_aggregation=bool(oz.get("pt_aggregation", False)),
        headcount_unit_field=str(oz.get("headcount_unit_field", "Worksite_ID")),
        citation=str(pack.get("credit", {}).get("statutory_citation", "")),
        pt_band_hours=pt_band_tuple,                                   # [H2]
        pt_weight=float(pt_weight) if pt_weight else None,             # [H2]
        measuring_date=str(resolved.get("measuring_date", oz.get("measuring_date", "last_day"))),  # [H3]
        entity_combination=str(oz.get("entity_combination", "permitted")),  # [I2]
        included_pay_codes=tuple(inc) if inc else None,               # [L5]
        excluded_pay_codes=tuple(exc) if exc else None,               # [L5]
        tax_year=tax_year,
        # Optional `methodology` block; absent means the certified v7 defaults,
        # so existing packs need no edit. See ENGINE-CONVERGENCE.md.
        methodology=OneZeroMethodology.from_pack_json(oz.get("methodology")),
    )


def apply_one_zero_state_credit(
    state: str,
    average_headcount: float,
    *,
    prior_period_average_headcount: float = 0.0,
    threshold_override: float | None = None,
) -> dict[str, Any]:
    """Apply a rule pack's benefit math on top of an already-computed One/Zero
    Average Headcount.

    `average_headcount` is the engine's `annual_average` (mean of 12 monthly
    unit headcounts, summed across units). `prior_period_average_headcount`
    is the comparable figure for the prior tax year — net-new qualifying jobs
    are the year-over-year delta minus the rule pack's statutory threshold.

    `threshold_override` ([L4] CALC-10) replaces the statutory minimum-new-jobs
    threshold with a NEGOTIATED value (e.g. an incentive agreement requiring
    "100 jobs at $18/hr"). None = use the pack's statutory threshold.

    This is the ONLY state-credit benefit entry point: the statutory One/Zero
    Average Headcount drives every dollar figure the UI shows.
    """
    state_u = state.upper()
    pack_file = STATE_TO_PACK.get(state_u)
    if pack_file is None:
        return _no_state_pack_result(state_u)

    pack = _load_pack(pack_file)
    threshold = float(threshold_override) if threshold_override is not None else float(pack["thresholds"]["minimum_new_jobs"])
    years = int(pack["benefit"]["benefit_period_years"])
    citation = pack["credit"]["statutory_citation"]
    benefit = pack["benefit"]
    net_new = max(0.0, float(average_headcount) - float(prior_period_average_headcount))
    qualifying = round(max(0.0, net_new - threshold), 2)

    if "amount_per_qualifying_job_usd" in benefit:
        per_job = float(benefit["amount_per_qualifying_job_usd"])
        annual = round(qualifying * per_job)
    elif "amount_per_qualifying_job_pct_of_wages" in benefit:
        pct = float(benefit["amount_per_qualifying_job_pct_of_wages"])
        avg_wage = _avg_state_wage(state_u)
        per_job = round(avg_wage * pct)
        annual = round(qualifying * per_job)
    else:
        raise ValueError(f"pack {pack_file} has no recognized benefit shape")

    lifetime = annual * years
    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step=f"Apply One/Zero Average Headcount to {pack['credit']['name']} benefit math",
            inputs={
                "average_headcount": float(average_headcount),
                "prior_period_average_headcount": float(prior_period_average_headcount),
                "threshold": threshold,
            },
            formula="qualifying = max(0, avg_headcount - prior_avg_headcount - threshold)",
            output={"qualifying_jobs": qualifying, "annual_credit_usd": annual, "lifetime_credit_usd": lifetime},
            citation=citation,
        )

    return {
        "state": state_u,
        "no_state_pack": False,
        "credit_code": pack["credit"]["code"],
        "credit_name": pack["credit"]["name"],
        "jurisdiction": pack["jurisdiction"]["code"],
        "citation": citation,
        "threshold": threshold,
        "qualifying_jobs": qualifying,
        "amount_per_job_usd": per_job,
        "annual_credit_usd": annual,
        "benefit_period_years": years,
        "lifetime_credit_usd": lifetime,
        "basis": "one_zero",
        "average_headcount": float(average_headcount),
        "prior_period_average_headcount": float(prior_period_average_headcount),
    }


def state_per_job_usd(state: str) -> float:
    """[O3] UX-06 — the statutory dollars-per-qualifying-job for a state.

    Returns 0.0 for a pct-of-wages program (e.g. NY) or a state with no pack,
    where a flat per-job figure isn't meaningful.
    """
    pack_file = STATE_TO_PACK.get(state.upper())
    if pack_file is None:
        return 0.0
    benefit = _load_pack(pack_file).get("benefit", {})
    return float(benefit.get("amount_per_qualifying_job_usd") or 0.0)


def combine_entity_credits(state: str, fein_breakdown: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """[I2] CALC-06 — credit for a program that PROHIBITS entity combination.

    Each legal entity (FEIN) is its own taxpayer: the statutory threshold is
    applied to each entity's Average Headcount independently and the resulting
    credits are summed — entities never merge. Returns the per-FEIN breakdown
    plus the combined totals so the route can surface both.
    """
    per_fein: dict[str, Any] = {}
    sum_annual = sum_lifetime = sum_qualifying = 0.0
    for fcode, agg in fein_breakdown.items():
        entity_credit = apply_one_zero_state_credit(state, agg["average_headcount"])
        per_fein[fcode] = {
            "average_headcount": agg["average_headcount"],
            "qualifying_jobs": entity_credit["qualifying_jobs"],
            "annual_credit_usd": entity_credit["annual_credit_usd"],
            "lifetime_credit_usd": entity_credit["lifetime_credit_usd"],
        }
        sum_annual += entity_credit["annual_credit_usd"]
        sum_lifetime += entity_credit["lifetime_credit_usd"]
        sum_qualifying += entity_credit["qualifying_jobs"]
    return {
        "per_fein": per_fein,
        "combined_annual_credit_usd": round(sum_annual),
        "combined_lifetime_credit_usd": round(sum_lifetime),
        "combined_qualifying_jobs": round(sum_qualifying, 2),
    }

