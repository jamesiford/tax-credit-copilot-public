"""Resolving one client-programme-year into the inputs the engine needs.

Every per-client read answers the same four questions before it can compute
anything: which programme does this state map to, what does the statute say
for this year, what is this client's fiscal window, and which payroll rows
fall inside it. Answering them separately is the point — conflating the window
with the tax year, or the statute with the methodology, is what pinned the old
sealed path to a single client.

Resolution declines loudly. An unauthored year, an unmapped state or an empty
window each raise rather than returning an empty population, because "nobody
qualifies" and "we cannot answer" are different answers and only one of them
is safe to show a client.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ClientRunNotAvailable(LookupError):
    """The question cannot be answered, and why.

    Returning an empty population instead would be indistinguishable from
    "nobody qualifies" — a different and far more dangerous answer.
    """


@dataclass(frozen=True)
class ResolvedStatute:
    """What a client-programme-year is judged BY, with no payroll attached.

    A read that answers from Gold still has to state the statute and the fiscal
    window — the page shows both, and the floors draw the near-floor band — but
    it has no reason to load a row of payroll to do it.
    """

    account_id: int | None
    state: str
    program_code: str
    tax_year: int
    floors: Any
    pack: Any
    window: Any


@dataclass(frozen=True)
class ClientRun:
    """One client-programme-year, resolved and ready to compute over."""

    account_id: int | None
    state: str
    program_code: str
    tax_year: int
    floors: Any
    pack: Any
    window: Any
    rows: list[dict[str, Any]]

    def engine_kwargs(self) -> dict[str, Any]:
        """The arguments both certified methods take, so neither can drift."""
        from domain.calculation.onezero import first_measurable_month

        return {
            "tax_year": self.tax_year,
            # NOT `window.begin`. A year opening mid-month opens on a stub whose
            # month-end no pay period reaches, which costs Month 1 and drops the
            # window's real final month off the end. See `first_measurable_month`.
            "analysis_start_month": first_measurable_month(
                self.rows, (self.window.begin, self.window.end)
            ),
            "pack": self.pack,
            "fiscal_window": (self.window.begin, self.window.end),
        }


def resolve_statute(
    *, account_id: int | None, state: str, tax_year: int
) -> ResolvedStatute:
    """Programme, floors, rule pack and fiscal window — no payroll.

    Declines exactly as `resolve_client_run` does, and for the same reasons: an
    unmapped state and an unauthored year are both real gaps in coverage, and
    pricing either from a neighbour is a wrong answer wearing a right one's
    costume [ADR-005].
    """
    from infrastructure.payroll.fiscal_source import client_fiscal_window
    from tools.credit_math import (
        PROGRAM_CODE_TO_PACK,
        STATE_TO_PACK,
        load_pack_one_zero,
        resolve_statutory_floors,
        resolve_tax_year_convention,
    )

    state = state.upper()

    pack_file = STATE_TO_PACK.get(state)
    program_code = next(
        (code for code, name in PROGRAM_CODE_TO_PACK.items() if name == pack_file), None
    )
    if program_code is None:
        raise ClientRunNotAvailable(f"no programme maps to state {state!r}")

    try:
        floors = resolve_statutory_floors(program_code, tax_year)
    except (FileNotFoundError, ValueError) as exc:
        # `load_year_pack` raises FileNotFoundError for an unauthored year. It is
        # a decline, not a server fault: the year is genuinely uncovered.
        raise ClientRunNotAvailable(str(exc)) from exc

    pack = load_pack_one_zero(state, tax_year=tax_year)
    if pack is None:
        raise ClientRunNotAvailable(f"no rule pack for {state} tax year {tax_year}")

    convention = resolve_tax_year_convention(program_code, tax_year)
    return ResolvedStatute(
        account_id=account_id,
        state=state,
        program_code=program_code,
        tax_year=tax_year,
        floors=floors,
        pack=pack,
        window=client_fiscal_window(account_id, tax_year, convention["label"]),
    )


def resolve_client_run(
    *,
    account_id: int | None,
    state: str,
    tax_year: int,
    rows: list[dict[str, Any]] | None = None,
) -> ClientRun:
    """Resolve statute, fiscal window and payroll for one client-programme-year.

    The compute path. A read answering from Gold wants `resolve_statute`
    instead, which stops before the payroll.

    `rows` lets a caller resolving several years for one client hand in the
    payroll it already loaded. Resolution is unchanged — the same state filter
    and the same window trim still apply — so a multi-year read cannot drift
    from a single-year one by taking a shortcut around this function.
    """
    from domain.calculation.headcount import row_state
    from infrastructure.payroll.pay_period_source import load_pay_periods

    statute = resolve_statute(
        account_id=account_id, state=state, tax_year=tax_year
    )
    state = statute.state
    window = statute.window

    source = load_pay_periods(account_id) if rows is None else rows
    rows = [r for r in source if row_state(r) == state]
    rows = [
        r for r in rows
        if window.begin.isoformat() <= str(r.get("Pay_Date") or "")[:10] <= window.end.isoformat()
    ]
    if not rows:
        scope = f" for account {account_id}" if account_id else ""
        raise ClientRunNotAvailable(
            f"no {state} payroll inside {window.begin}..{window.end}{scope}"
        )

    return ClientRun(
        account_id=account_id,
        state=state,
        program_code=statute.program_code,
        tax_year=tax_year,
        floors=statute.floors,
        pack=statute.pack,
        window=window,
        rows=rows,
    )
