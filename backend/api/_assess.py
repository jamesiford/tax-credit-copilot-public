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
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from api._payperiods import row_state, unauthored_state_years
from domain.calculation.headcount import average_headcount as _average_headcount
from domain.calculation.headcount import rows_for_state_year as _rows_for_state_year
from domain.claims import ClaimStatus, ProgramClaim, Provenance


def _fiscal_years(rows: list[dict[str, Any]]) -> list[int]:
    """Tax years present in the payroll, by pay date.

    Deliberately NOT via `fiscal_year_of`: that labels a fiscal year by the year
    it ends, while Georgia's regulation labels a tax year by the year it begins,
    and the two disagree for every non-calendar filer. See the strict xfail in
    `tests/test_ga_wage_table.py`. Until the partner rules, this uses the pay date's own
    year, which is the reading the certified reference run already uses.
    """
    years = set()
    for row in rows:
        pay_date = str(row.get("Pay_Date") or "")[:10]
        if pay_date:
            years.add(date.fromisoformat(pay_date).year)
    return sorted(years)


def rows_for_state_year(
    rows: list[dict[str, Any]],
    state: str,
    tax_year: int,
    window: tuple[date, date] | None = None,
) -> list[dict[str, Any]]:
    """Re-exported from `domain.calculation.headcount`.

    Average Headcount is a statutory quantity, so its definition lives in the
    domain. This name is kept because several callers already import it here,
    and a second implementation would be a second answer.
    """
    return _rows_for_state_year(rows, state, tax_year, window)


def average_headcount(
    rows: list[dict[str, Any]],
    state: str,
    tax_year: int,
    pack: Any,
    window: tuple[date, date] | None = None,
) -> float:
    """Re-exported from `domain.calculation.headcount`. See above."""
    return _average_headcount(rows, state, tax_year, pack, window)


#: Months of payroll a fiscal year needs before it is worth averaging over
#: twelve. Matches `_MIN_REACHABLE_MONTHS` in the unit trend, which declines a
#: year for the same reason.
_MIN_MONTHS_TO_ASSESS = 6


def _months_with_payroll(rows: list[dict[str, Any]]) -> int:
    """Distinct calendar months the selected rows actually pay into."""
    return len({str(r.get("Pay_Date") or "")[:7] for r in rows if r.get("Pay_Date")})


def _client_window(client_id: int, state: str, tax_year: int) -> tuple[date, date] | None:
    """The client's own fiscal year, or None to fall back to the calendar year.

    Resolved by the same adapter the certified run uses. Without it a
    non-calendar filer is measured over the wrong twelve months: Candle Bottle
    came out at 226.76 against a certified 494.25, because five months of its
    payroll landed inside calendar 2023 and the other seven measuring dates
    scored zero.
    """
    from infrastructure.payroll.fiscal_source import window_for_state_year

    return window_for_state_year(client_id, state, tax_year)


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
    from tools.credit_math import (
        PROGRAM_CODE_TO_PACK,
        STATE_TO_PACK,
        apply_one_zero_state_credit,
        authored_years,
        load_pack_one_zero,
    )

    pack_to_program = {pack: code for code, pack in PROGRAM_CODE_TO_PACK.items()}
    requested = sorted(tax_years) if tax_years else _fiscal_years(rows)
    if not requested:
        return {"assessed": [], "declined": [], "years": []}

    #: Net-new is measured against the year before. That year is an INPUT, so it
    #: is computed even when nobody asked for it -- a single-year run used to
    #: leave the prior year missing and fall back to a base of zero, which made
    #: every job look net-new and inflated the figure roughly tenfold.
    #: Claims are still only RECORDED for the years actually requested.
    years = sorted(set(requested) | {year - 1 for year in requested})

    states = sorted({row_state(r) for r in rows if row_state(r)})
    wanted = program_code.upper() if program_code else None

    # Average Headcount per (state, year) first. Net-new needs the PRIOR year's
    # figure, so a single pass in year order would have nothing to compare the
    # earliest year against.
    averages: dict[tuple[str, int], float] = {}
    declined: list[dict[str, Any]] = []

    for state in states:
        pack_file = STATE_TO_PACK.get(state)
        code = pack_to_program.get(pack_file) if pack_file else None
        if not code or (wanted and code != wanted):
            continue

        # [ADR-005] A program with no authored years is describable, not
        # calculable. `load_pack_one_zero` would still hand back a flat pack and
        # we would compute a confident figure under no particular year's
        # statute — and the scope selector already tells the operator that
        # program cannot be priced. One source of truth, so the two agree.
        priceable = set(authored_years(pack_file))
        if not priceable:
            declined.append({
                "program_code": code,
                "tax_year": None,
                "reason": "program_not_year_scoped",
                "detail": (
                    f"{code} has no year-scoped rule packs. ADR-005: a figure "
                    f"computed without a year-resolved statute is not a "
                    f"statutory figure."
                ),
            })
            continue

        for year in years:
            if year not in priceable:
                if year in requested:
                    declined.append({
                        "program_code": code,
                        "tax_year": year,
                        "reason": "no_authored_statute",
                        "detail": (
                            f"No rule pack for {code} tax year {year}. "
                            f"Authored: {', '.join(str(y) for y in sorted(priceable))}."
                        ),
                    })
                continue

            pack = load_pack_one_zero(state, tax_year=year)
            if pack is None:
                continue

            # The CLIENT's twelve months, not January to December. A
            # non-calendar filer measured over the calendar year scores every
            # month before its first pay date as zero and still divides by 12.
            window = _client_window(client_id, state, year)
            year_rows = rows_for_state_year(rows, state, year, window)
            if len(year_rows) < 50:  # too thin to mean anything
                continue

            # An OPEN year is never claimed. A claim is a fact about a closed
            # year, and pricing eight months over twelve would re-rank the book
            # on a fraction of a year. How am I doing reads it instead.
            from application.open_year import is_open

            if window is not None and is_open(window[1]):
                if year in requested:
                    declined.append({
                        "program_code": code,
                        "tax_year": year,
                        "reason": "year_in_progress",
                        "detail": (
                            f"TY{year} is still open (its fiscal year ends {window[1]}). "
                            f"It is read in-year on How am I doing, and claimed once it closes."
                        ),
                    })
                continue

            # A year the payroll barely touches is DECLINED, not priced at zero
            # — the same rule the unit trend applies. Candle Bottle's payroll
            # stops 2024-08-09 while its TY2024 window runs to Aug 2025, so the
            # row count clears the guard above on about a week of data and the
            # year would publish as "assessed, no credit identified".
            months = _months_with_payroll(year_rows)
            if months < _MIN_MONTHS_TO_ASSESS:
                if year in requested:
                    declined.append({
                        "program_code": code,
                        "tax_year": year,
                        "reason": "payroll_too_thin",
                        "detail": (
                            f"Payroll covers {months} month(s) of the {year} fiscal "
                            f"year. A twelve-month average would be mostly zeroes."
                        ),
                    })
                continue

            averages[(state, year)] = average_headcount(rows, state, year, pack, window)

    assessed: list[dict[str, Any]] = []
    for (state, year), average in sorted(averages.items()):
        if year not in requested:
            continue  # computed only to serve as the next year's base
        pack_file = STATE_TO_PACK.get(state)
        code = pack_to_program.get(pack_file)
        if not code:
            continue

        # Two different reasons the prior year can be missing, and only one of
        # them used to be handled. If the year before HAS payroll it is computed
        # above and compared against properly. If it genuinely has none, this is
        # the earliest year held, so it is its own base -- which is what
        # `unit_year_master` already records for an inferred base year. The old
        # `0.0` fallback asserted that nobody worked here the year before and
        # made the entire headcount net-new.
        prior = averages.get((state, year - 1))
        is_base_year = prior is None
        base = average if is_base_year else prior
        credit = apply_one_zero_state_credit(
            state, average, prior_period_average_headcount=base,
        )
        identified = Decimal(str(credit.get("annual_credit_usd") or 0))

        claim = ProgramClaim(
            client_id=client_id,
            program_code=code,
            tax_year=year,
            status=ClaimStatus.ASSESSED,
            provenance=Provenance.COMPUTED,
            identified_usd=identified,
            # The jobs reasoning, not just the dollar figure. A cell at $0 is
            # either one hire short or fifty, and only these tell them apart.
            average_headcount=round(average, 2),
            base_average_headcount=round(base, 2),
            threshold_jobs=float(credit.get("threshold") or 0),
            is_base_year=is_base_year,
            assumption_set_id=credit.get("assumption_set_id"),
            rule_pack_version=str(pack_file),
            decided_by=assessed_by,
        )

        if repository is not None:
            existing = repository.current(client_id, code, year)
            if existing is not None and existing.status is not ClaimStatus.NOT_ASSESSED:
                # A recalculation is new EVIDENCE, not a new decision. Someone
                # already proposed, filed or declined this cell; resetting it to
                # `assessed` would erase that and re-propose something the
                # client has already answered.
                from dataclasses import replace
                import uuid
                from datetime import datetime, timezone

                moment = datetime.now(timezone.utc)
                claim = replace(
                    existing,
                    claim_id=str(uuid.uuid4()),
                    identified_usd=identified,
                    average_headcount=claim.average_headcount,
                    base_average_headcount=claim.base_average_headcount,
                    threshold_jobs=claim.threshold_jobs,
                    is_base_year=claim.is_base_year,
                    assumption_set_id=claim.assumption_set_id,
                    rule_pack_version=claim.rule_pack_version,
                    decided_by=assessed_by,
                    decided_at=moment,
                    effective_from=moment,
                    effective_to=None,
                )
            repository.record(claim)

        assessed.append(claim.to_dict())

    return {
        "assessed": assessed,
        "declined": declined,
        "years": requested,
        "states": states,
    }
