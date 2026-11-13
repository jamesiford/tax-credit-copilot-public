"""Credit-math tools: apply a JSON rule pack to a statutory headcount figure."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from domain.calculation.floors import StatutoryFloors, program_name
from domain.calculation.trail import current_recorder
from tools.pack_lookup import pack_file_for
from tools.program_registry import RegistryView, load_registry, rules_dir

# Two-letter state -> rule pack filename, and program code (as it appears in a pack's `credit.code`) -> pack
# filename. Both are READ-ONLY VIEWS over the program registry (`rules/registry/programs.json`, ADR-013): adding a
# program is a manifest entry plus a pack, with no edit here. They keep their old names and compare equal to the
# dictionaries they replace, so every import site is unchanged. States with no entry (e.g. TX) flow through
# apply_one_zero_state_credit() and get a structured "no_state_pack" response. An assumption set names the programme
# it measures by code, not by state, because a state can run several credits.
STATE_TO_PACK: Mapping[str, str] = RegistryView("state")
PROGRAM_CODE_TO_PACK: Mapping[str, str] = RegistryView("code")


def __getattr__(name: str):
    """`_RULES` stays importable, resolved at read time so `RULES_DIR` is honoured."""
    if name == "_RULES":
        return rules_dir()
    raise AttributeError(name)


def _load_pack(filename: str) -> dict[str, Any]:
    path = rules_dir() / filename
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
    return (rules_dir() / _program_name(pack_file)).is_dir()


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
        authored = sorted(int(p.stem) for p in (rules_dir() / program).glob("*.json") if p.stem.isdigit())
        if tax_year is None:
            # Describing a program ("what is GA JTC?") is a legitimate call and
            # should not raise. Return the most recent authored year with
            # year_resolved=False — any CALCULATION path must require True,
            # because a credit cannot be computed without knowing which year's
            # statute applies.
            if not authored:
                return _load_pack(pack_file), False
            latest = rules_dir() / program / f"{authored[-1]}.json"
            return json.loads(latest.read_text(encoding="utf-8")), False
        path = rules_dir() / program / f"{tax_year}.json"
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
    directory = rules_dir() / program
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
    from tools.program_credit import avg_program_wage

    return avg_program_wage(state)


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
    from tools.one_zero_pack import build_one_zero_pack  # local import: avoid load-time cycle

    s = state_or_code.upper()
    pack_file = pack_file_for(s)
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

    return build_one_zero_pack(pack, resolved, (inc, exc), tax_year)


def apply_one_zero_state_credit(
    state: str,
    average_headcount: float,
    *,
    prior_period_average_headcount: float = 0.0,
    threshold_override: float | None = None,
) -> dict[str, Any]:
    """The state-named entry point: prices a state's DEFAULT program. Takes a program code too. [F04c.4]

    The body lives in `tools/program_credit.py`, keyed by program, so a state with several programs can price each.
    """
    from tools.program_credit import apply_one_zero_program_credit

    return apply_one_zero_program_credit(
        state, average_headcount,
        prior_period_average_headcount=prior_period_average_headcount, threshold_override=threshold_override,
    )


def state_per_job_usd(state: str) -> float:
    """[O3] UX-06: dollars per qualifying job for a state's default program (or a program code); see `program_credit`."""
    from tools.program_credit import program_per_job_usd

    return program_per_job_usd(state)


def combine_entity_credits(state: str, fein_breakdown: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """[I2] CALC-06: per-entity credit for a no-combination program; see `program_credit.combine_program_entity_credits`."""
    from tools.program_credit import combine_program_entity_credits

    return combine_program_entity_credits(state, fein_breakdown)
