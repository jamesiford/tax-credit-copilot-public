"""Assess a client's programme-years and record what the engine computes.

The bridge between the calculation engine and the claim store. Running it turns
a coverage cell from `not_assessed` into `assessed` with a real `identified_usd`
behind it, which is what makes the B4 matrix a computed artifact rather than a
fixture.

Two rules govern this module.

**Every year is calculated under its own statute.** [ADR-005] Applying 2025
rules to 2021 payroll is not an approximation, it is a wrong answer, so a year
with no authored rule pack is DECLINED by name rather than estimated from a
neighbour.

**Nothing is overwritten.** Re-assessing appends a record; the prior belief and
the run behind it stay readable. A cell that has moved past `assessed` — someone
proposed it, filed it, or the client declined it — keeps its status and only its
`identified_usd` is refreshed, because a recalculation is new evidence, not a
new decision.

This was `api/_assess.py`. It holds no routing, so it moved out of the router package
once the payroll reader it depends on stopped raising `HTTPException`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.assessment_inputs import (
    MIN_MONTHS_TO_ASSESS,
    MIN_ROWS_TO_ASSESS,
    average_headcount,
    client_window,
    fiscal_years,
    months_with_payroll,
    rows_for_state_year,
)
from application.assessment_claims import priced_claim, program_of, refreshed
from application.open_year import is_open
from application.payroll_rows import row_state
from domain.claims import ClaimStatus


@dataclass
class _Sweep:
    """Average Headcount per (state, year), and what could not be computed and why.

    Net-new needs the PRIOR year's figure, so every year is averaged first and the
    claims are priced in a second pass; a single pass in year order would have
    nothing to compare the earliest year against.
    """

    client_id: int
    rows: list[dict[str, Any]]
    requested: list[int]
    years: list[int]
    wanted: str | None
    averages: dict[tuple[str, int], float] = field(default_factory=dict)
    declined: list[dict[str, Any]] = field(default_factory=list)

    def run(self, states: list[str]) -> None:
        for state in states:
            self._state(state)

    def _decline(self, code: str, year: int | None, reason: str, detail: str, *, only_if_requested: bool = True) -> None:
        if only_if_requested and year not in self.requested:
            return
        self.declined.append({"program_code": code, "tax_year": year, "reason": reason, "detail": detail})

    def _state(self, state: str) -> None:
        from tools.credit_math import authored_years

        pack_file, code = program_of(state)
        if not code or (self.wanted and code != self.wanted):
            return
        # [ADR-005] A program with no authored years is describable, not
        # calculable. `load_pack_one_zero` would still hand back a flat pack and
        # we would compute a confident figure under no particular year's
        # statute — and the scope selector already tells the operator that
        # program cannot be priced. One source of truth, so the two agree.
        priceable = set(authored_years(pack_file))
        if not priceable:
            self._decline(
                code, None, "program_not_year_scoped",
                f"{code} has no year-scoped rule packs. ADR-005: a figure "
                f"computed without a year-resolved statute is not a "
                f"statutory figure.",
                only_if_requested=False,
            )
            return
        for year in self.years:
            if year in priceable:
                self._year(state, code, year)
            else:
                self._decline(
                    code, year, "no_authored_statute",
                    f"No rule pack for {code} tax year {year}. "
                    f"Authored: {', '.join(str(y) for y in sorted(priceable))}.",
                )

    def _year(self, state: str, code: str, year: int) -> None:
        from tools.credit_math import load_pack_one_zero

        pack = load_pack_one_zero(state, tax_year=year)
        if pack is None:
            return
        # The CLIENT's twelve months, not January to December. A non-calendar
        # filer measured over the calendar year scores every month before its
        # first pay date as zero and still divides by 12.
        window = client_window(self.client_id, state, year)
        year_rows = rows_for_state_year(self.rows, state, year, window)
        if len(year_rows) < MIN_ROWS_TO_ASSESS:  # too thin to mean anything
            return
        # An OPEN year is never claimed. A claim is a fact about a closed
        # year, and pricing eight months over twelve would re-rank the book
        # on a fraction of a year. How am I doing reads it instead.
        if window is not None and is_open(window[1]):
            self._decline(
                code, year, "year_in_progress",
                f"TY{year} is still open (its fiscal year ends {window[1]}). "
                f"It is read in-year on How am I doing, and claimed once it closes.",
            )
            return
        # A year the payroll barely touches is DECLINED, not priced at zero
        # — the same rule the unit trend applies. Candle Bottle's payroll
        # stops 2024-08-09 while its TY2024 window runs to Aug 2025, so the
        # row count clears the guard above on about a week of data and the
        # year would publish as "assessed, no credit identified".
        months = months_with_payroll(year_rows)
        if months < MIN_MONTHS_TO_ASSESS:
            self._decline(
                code, year, "payroll_too_thin",
                f"Payroll covers {months} month(s) of the {year} fiscal "
                f"year. A twelve-month average would be mostly zeroes.",
            )
            return
        self.averages[(state, year)] = average_headcount(self.rows, state, year, pack, window)


def _assessed_cells(sweep: _Sweep, assessed_by: str, repository: Any) -> list[dict[str, Any]]:
    assessed: list[dict[str, Any]] = []
    for (state, year), average in sorted(sweep.averages.items()):
        if year not in sweep.requested:
            continue  # computed only to serve as the next year's base
        claim = priced_claim(
            sweep.client_id, state, year, average, sweep.averages.get((state, year - 1)), assessed_by,
        )
        if claim is None:
            continue
        if repository is not None:
            existing = repository.current(sweep.client_id, claim.program_code, year)
            if existing is not None and existing.status is not ClaimStatus.NOT_ASSESSED:
                claim = refreshed(existing, claim, assessed_by)
            repository.record(claim)
        assessed.append(claim.to_dict())
    return assessed


def assess_client(
    client_id: int,
    rows: list[dict[str, Any]],
    *,
    program_code: str | None = None,
    tax_years: list[int] | None = None,
    assessed_by: str = "engine",
    repository=None,
) -> dict[str, Any]:
    """Run the engine over a client's payroll and record each programme-year.

    Returns the assessed cells plus anything declined, so a caller can report
    coverage honestly instead of presenting a partial sweep as a complete one.
    """
    requested = sorted(tax_years) if tax_years else fiscal_years(rows)
    if not requested:
        return {"assessed": [], "declined": [], "years": []}

    #: Net-new is measured against the year before. That year is an INPUT, so it
    #: is computed even when nobody asked for it -- a single-year run used to
    #: leave the prior year missing and fall back to a base of zero, which made
    #: every job look net-new and inflated the figure roughly tenfold.
    #: Claims are still only RECORDED for the years actually requested.
    years = sorted(set(requested) | {year - 1 for year in requested})
    states = sorted({row_state(r) for r in rows if row_state(r)})
    sweep = _Sweep(
        client_id, rows, requested, years, program_code.upper() if program_code else None,
    )
    sweep.run(states)
    return {
        "assessed": _assessed_cells(sweep, assessed_by, repository),
        "declined": sweep.declined,
        "years": requested,
        "states": states,
    }
