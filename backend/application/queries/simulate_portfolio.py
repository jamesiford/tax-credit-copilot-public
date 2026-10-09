"""What-if across every client in a state, not one at a time.

Shashi Bhushan, 28 August 2026:

> "I don't want to show just like 1 customer, one thing like how the partner wants. I
> want it like more powerful. Like, hey, use your corpus of data... these are
> the incentives for a certain state. And these are your customers currently
> operating in that state. Let's run your what-if scenario... That has to be run
> across multiple customers. And that is the power."

The single-client what-if answers *"what would this client get?"*. This answers
*"we hold a statute for this state — across everyone operating there, who moves
if we act, and what is it worth?"* Same engine, same statute, run across the
book.

Two things make the portfolio answer different from a stack of single answers,
and both are the reason this is a distinct query rather than a loop in a router:

**A client already over the threshold is not an opportunity.** Adding hours to
somebody who already qualifies changes their credit, not their eligibility. The
portfolio question is *who crosses*, and ranking by dollar delta buries the
client one hire short — their delta today is zero, the same zero as a client
fifty short.

**A year with no authored statute must be declined by name, not skipped.** A
sweep that quietly omitted clients would present a partial answer as a complete
one, which is exactly the failure ADR-005 exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query

_ACTIONS = ("add_headcount", "remove_headcount", "adjust_hours", "adjust_wages")


@dataclass(frozen=True)
class SimulatePortfolioQuery(Query):
    """One lever, applied to every client operating in one state-year.

    `state` and `tax_year` together select the statute [ADR-005]. Running a
    single lever across clients measured under different statutes would produce
    a total that means nothing.
    """

    tax_year: int
    state: str
    action: str = "add_headcount"
    magnitude: float = 5.0
    limit: int = 50

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError(f"action must be one of {_ACTIONS}, got {self.action!r}")


class PortfolioSimulationNotAvailable(LookupError):
    """The question cannot be answered for this state-year, and why."""


def handle_simulate_portfolio(query: SimulatePortfolioQuery) -> dict[str, Any]:
    from domain.calculation.headcount import average_headcount, rows_for_state_year
    from infrastructure.payroll.fiscal_source import window_for_state_year
    from infrastructure.payroll.pay_period_source import load_portfolio_pay_periods
    from tools.credit_math import (
        PROGRAM_CODE_TO_PACK,
        STATE_TO_PACK,
        load_pack_one_zero,
    )
    from tools.simulation import apply_onezero_lever, onezero_snapshot

    state = query.state.upper()

    pack_file = STATE_TO_PACK.get(state)
    program_code = next(
        (code for code, name in PROGRAM_CODE_TO_PACK.items() if name == pack_file), None
    )
    if program_code is None:
        raise PortfolioSimulationNotAvailable(f"no programme maps to state {state!r}")

    try:
        pack = load_pack_one_zero(state, tax_year=query.tax_year)
    except FileNotFoundError as exc:
        # `load_pack_one_zero` raises for an unauthored year rather than
        # returning None [ADR-005]. Either way the answer is the same: decline
        # by name. Pricing the year under a neighbour's statute would be a wrong
        # answer that looks like a right one.
        raise PortfolioSimulationNotAvailable(
            f"{state} has no authored statute for tax year {query.tax_year}. "
            f"Pricing it under another year's rules would be a wrong answer, "
            f"not an approximation. ({exc})"
        ) from exc

    if pack is None:
        raise PortfolioSimulationNotAvailable(
            f"{state} has no authored statute for tax year {query.tax_year}. "
            f"Pricing it under another year's rules would be a wrong answer, "
            f"not an approximation."
        )

    try:
        prior_pack = load_pack_one_zero(state, tax_year=query.tax_year - 1)
    except FileNotFoundError:
        # No prior year authored means no frozen base to measure against. That
        # is a real limitation, not an error — the sweep proceeds with a zero
        # base and every client's whole workforce reads as net-new, which the
        # response discloses rather than hides.
        prior_pack = None

    results: list[dict[str, Any]] = []
    declined: list[dict[str, Any]] = []

    for client_id, all_rows in sorted(load_portfolio_pay_periods().items()):
        # The CLIENT's twelve months. Leaving this on the calendar year while
        # the assessment moved to the real window is how the sweep and the
        # coverage matrix come to quote different figures for one client-year.
        window = window_for_state_year(client_id, state, query.tax_year)
        rows = rows_for_state_year(all_rows, state, query.tax_year, window)
        if not rows:
            continue

        # The frozen base the credit is measured against. Omitting it treats the
        # whole workforce as net-new and overstates the credit enormously — and
        # produces a different figure from the coverage matrix for the same
        # client-year, which is indefensible whichever is right.
        base = (
            average_headcount(
                all_rows, state, query.tax_year - 1, prior_pack,
                window_for_state_year(client_id, state, query.tax_year - 1),
            )
            if prior_pack is not None
            else 0.0
        )

        try:
            before = onezero_snapshot(
                rows, tax_year=query.tax_year, state=state, pack=pack,
                prior_average_headcount=base,
            )
            moved, _detail = apply_onezero_lever(
                rows,
                action=query.action,
                magnitude=query.magnitude,
                pack=pack,
                state=state,
            )
            after = onezero_snapshot(
                moved, tax_year=query.tax_year, state=state, pack=pack,
                prior_average_headcount=base,
            )
        except Exception as exc:  # noqa: BLE001 — one client must not kill the sweep
            declined.append({"client_id": client_id, "reason": str(exc)})
            continue

        delta = after["annual_credit_usd"] - before["annual_credit_usd"]
        qualified_before = before["annual_credit_usd"] > 0
        qualified_after = after["annual_credit_usd"] > 0

        results.append(
            {
                "client_id": client_id,
                "base_average_headcount": round(base, 2),
                "average_headcount_before": before["average_headcount"],
                "average_headcount_after": after["average_headcount"],
                "annual_credit_before_usd": before["annual_credit_usd"],
                "annual_credit_after_usd": after["annual_credit_usd"],
                "annual_credit_delta_usd": delta,
                "qualified_before": qualified_before,
                "qualified_after": qualified_after,
                # The headline: this lever is what turns nothing into something.
                "crosses_threshold": not qualified_before and qualified_after,
            }
        )

    # Clients who CROSS come first — a client going from nothing to something is
    # a different kind of result from one already earning who earns more, and
    # ranking purely by dollars hides them behind established earners.
    results.sort(
        key=lambda r: (not r["crosses_threshold"], -r["annual_credit_delta_usd"])
    )

    crossings = [r for r in results if r["crosses_threshold"]]
    method_note = (
        "Every client is measured under the same statute for this state and "
        "tax year, against their own frozen prior-year base. Clients who "
        "cross the statutory threshold are listed first: going from no "
        "credit to a credit is a different result from an existing credit "
        "growing, and ranking on dollars alone hides the crossings behind "
        "established earners."
    )
    if prior_pack is None:
        # Stated, not implied. With no prior year authored there is no base to
        # subtract, so every client's whole workforce counts as net-new and the
        # figures are upper bounds rather than projections.
        method_note += (
            f" NOTE: {state} has no authored statute for {query.tax_year - 1}, "
            f"so there is no frozen base. Every client's entire workforce is "
            f"treated as net-new and these figures are upper bounds, not "
            f"projections."
        )

    return {
        "state": state,
        "program_code": program_code,
        "tax_year": query.tax_year,
        "action": query.action,
        "magnitude": query.magnitude,
        "has_frozen_base": prior_pack is not None,
        "clients_evaluated": len(results),
        "clients_crossing_threshold": len(crossings),
        "credit_unlocked_usd": round(
            sum(r["annual_credit_delta_usd"] for r in crossings), 2
        ),
        "credit_delta_total_usd": round(
            sum(r["annual_credit_delta_usd"] for r in results), 2
        ),
        "clients": results[: query.limit],
        "declined": declined,
        "method_note": method_note,
    }
