"""Credit math keyed by PROGRAM: the benefit step of a rule pack over an already-computed Average Headcount. [F04c.4]

`tools/credit_math.py` keeps the state-named entry points (`apply_one_zero_state_credit`, `state_per_job_usd`,
`combine_entity_credits`) as thin wrappers over these. Each function here takes a program code OR a state: a state resolves to
its DEFAULT program (the first registered for it), so a state with one program prices exactly as it always did and a state
with several can price each program by naming it. No number moves for an existing program: the bodies are the ones that used
to live in `credit_math`, with the pack found through `pack_file_for` instead of `STATE_TO_PACK`.
"""
from __future__ import annotations

from typing import Any

from domain.calculation.trail import current_recorder
from tools.program_registry import program_for_code


def _resolve(key: str) -> tuple[str, str | None, str]:
    """`(upper key, pack file or None, state)` for a program code or a state."""
    from tools import credit_math

    key_u = key.upper()
    entry = program_for_code(key_u)
    return key_u, credit_math.pack_file_for(key_u), (entry.state if entry and entry.state else key_u)


def credit_key(program_code: str | None, state: str) -> str:
    """The key a credit is priced by: the named program, else the state (its default program)."""
    return program_code or state


def state_of(program_or_state: str) -> str:
    """The state a program code is priced in, or the (upper-cased) state itself when given one."""
    return _resolve(program_or_state)[2]


def avg_program_wage(program_or_state: str) -> float:
    """Average annual wage of the payroll rows in the program's state (used by percentage-of-wages benefits)."""
    from .payroll import _load_rows

    state = _resolve(program_or_state)[2]
    rows = [r for r in _load_rows() if r["location_state"] == state]
    return sum(r["annual_wage"] for r in rows) / len(rows) if rows else 0.0


def program_per_job_usd(program_or_state: str) -> float:
    """[O3] UX-06: the statutory dollars per qualifying job. 0.0 for a pct-of-wages program or an unregistered key."""
    from tools import credit_math

    pack_file = _resolve(program_or_state)[1]
    if pack_file is None:
        return 0.0
    return float(credit_math._load_pack(pack_file).get("benefit", {}).get("amount_per_qualifying_job_usd") or 0.0)


def _benefit_amounts(benefit: dict[str, Any], qualifying: float, key: str, pack_file: str) -> tuple[float, float]:
    """`(per job, annual credit)` for whichever benefit shape the pack declares."""
    if "amount_per_qualifying_job_usd" in benefit:
        per_job = float(benefit["amount_per_qualifying_job_usd"])
    elif "amount_per_qualifying_job_pct_of_wages" in benefit:
        per_job = round(avg_program_wage(key) * float(benefit["amount_per_qualifying_job_pct_of_wages"]))
    else:
        raise ValueError(f"pack {pack_file} has no recognized benefit shape")
    return per_job, round(qualifying * per_job)


def _record_step(pack: dict[str, Any], average: float, prior: float, threshold: float, figures: tuple[float, int, int]) -> None:
    """Put the benefit step into the active calculation trail, when one is recording."""
    recorder = current_recorder()
    if recorder is None:
        return
    qualifying, annual, lifetime = figures
    recorder.record(
        step=f"Apply One/Zero Average Headcount to {pack['credit']['name']} benefit math",
        inputs={"average_headcount": average, "prior_period_average_headcount": prior, "threshold": threshold},
        formula="qualifying = max(0, avg_headcount - prior_avg_headcount - threshold)",
        output={"qualifying_jobs": qualifying, "annual_credit_usd": annual, "lifetime_credit_usd": lifetime},
        citation=pack["credit"]["statutory_citation"],
    )


def apply_one_zero_program_credit(
    program_or_state: str,
    average_headcount: float,
    *,
    prior_period_average_headcount: float = 0.0,
    threshold_override: float | None = None,
) -> dict[str, Any]:
    """Apply a rule pack's benefit math on top of an already-computed One/Zero Average Headcount.

    Net-new qualifying jobs are the year-over-year delta minus the pack's statutory threshold; `threshold_override`
    ([L4] CALC-10) replaces it with a NEGOTIATED value. This is the ONLY benefit entry point: the statutory One/Zero Average
    Headcount drives every dollar figure the UI shows. An unregistered key returns the structured `no_state_pack` answer.
    """
    from tools import credit_math

    key, pack_file, state = _resolve(program_or_state)
    if pack_file is None:
        return credit_math._no_state_pack_result(state)

    return credit_from_pack(credit_math._load_pack(pack_file), (key, state, pack_file), average_headcount,
                            prior_period_average_headcount, threshold_override)


def credit_from_pack(
    pack: dict[str, Any], names: tuple[str, str, str], average_headcount: float, prior_period_average_headcount: float = 0.0,
    threshold_override: float | None = None,
) -> dict[str, Any]:
    """The benefit step over a pack document already in hand: `names` is `(key, state, pack file)`.

    The one body behind `apply_one_zero_program_credit` (which loads the pack from the rules folder) and the portal's draft
    preview (which holds a draft's document in memory and must not write it anywhere), so a preview prices with the engine's
    own formula and not a second copy of it.
    """
    key, state, pack_file = names
    average, prior = float(average_headcount), float(prior_period_average_headcount)
    threshold = float(threshold_override) if threshold_override is not None else float(pack["thresholds"]["minimum_new_jobs"])
    years = int(pack["benefit"]["benefit_period_years"])
    qualifying = round(max(0.0, max(0.0, average - prior) - threshold), 2)
    per_job, annual = _benefit_amounts(pack["benefit"], qualifying, key, pack_file)
    _record_step(pack, average, prior, threshold, (qualifying, annual, annual * years))
    return _result(pack, state, (average, prior, threshold, qualifying), (per_job, annual, years))


def _result(pack: dict[str, Any], state: str, inputs: tuple[float, ...], money: tuple[float, int, int]) -> dict[str, Any]:
    """The structured credit answer every caller reads."""
    average, prior, threshold, qualifying = inputs
    per_job, annual, years = money
    return {
        "state": state,
        "no_state_pack": False,
        "credit_code": pack["credit"]["code"],
        "credit_name": pack["credit"]["name"],
        "jurisdiction": pack["jurisdiction"]["code"],
        "citation": pack["credit"]["statutory_citation"],
        "threshold": threshold,
        "qualifying_jobs": qualifying,
        "amount_per_job_usd": per_job,
        "annual_credit_usd": annual,
        "benefit_period_years": years,
        "lifetime_credit_usd": annual * years,
        "basis": "one_zero",
        "average_headcount": average,
        "prior_period_average_headcount": prior,
    }

def combine_program_entity_credits(program_or_state: str, fein_breakdown: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """[I2] CALC-06: credit for a program that PROHIBITS entity combination.

    Each legal entity (FEIN) is its own taxpayer: the threshold is applied to each entity's Average Headcount independently
    and the credits are summed, so entities never merge. Returns the per-FEIN breakdown plus the combined totals.
    """
    per_fein: dict[str, Any] = {}
    sum_annual = sum_lifetime = sum_qualifying = 0.0
    for fcode, agg in fein_breakdown.items():
        entity_credit = apply_one_zero_program_credit(program_or_state, agg["average_headcount"])
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
