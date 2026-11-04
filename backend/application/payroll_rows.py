"""Loading pay-period rows and walking the rule packs, without a web framework.

This was `api/_payperiods.py`, and it raised `HTTPException`: the reader of payroll
could not be called by a use case, a notebook or a scheduled job without dragging
FastAPI in, so the one application service that needed it (`assess_client`) stayed
filed under the router package. It raises ordinary errors now; the router package's
`_payperiods` translates them to the status codes callers have always seen.

One source of truth for "give me the pay-period rows and walk the rule packs", shared
by the One/Zero reads, the retroactive scan, the performance views and the assessment.
"""
from __future__ import annotations

from typing import Any, Iterable, Iterator

from application.qc_resolutions import apply_calc_drops
from application.source_ports import (
    configured_account_id,
    load_pay_periods,
    load_portfolio_pay_periods,
)
from domain.calculation.headcount import row_state as _row_state
from domain.calculation.headcount import states_present as _states_present

__all__ = [
    "NoPayrollForClient", "PayrollDatasetNotGenerated", "PayrollNotAvailable",
    "configured_account_id", "iter_state_packs", "load_pay_periods",
    "load_portfolio_pay_periods", "require_pay_periods", "row_state", "states_present",
    "unauthored_state_years",
]

NOT_GENERATED_DETAIL = (
    "Pay-period dataset not generated. Run `python data/generate_pay_periods.py`."
)


class PayrollNotAvailable(LookupError):
    """There is no payroll to answer from; the subclass says which kind of absence."""


class NoPayrollForClient(PayrollNotAvailable):
    """A named client has no rows.

    A different fact from an absent dataset: telling the caller to go generate
    fixtures when they asked for client 42 sends them somewhere useless.
    """


class PayrollDatasetNotGenerated(PayrollNotAvailable):
    """The default dataset has not been generated at all."""


def require_pay_periods(*, drop_qc: bool = False, account_id: int | None = None) -> list[dict[str, Any]]:
    """Load the pay-period rows or raise `PayrollNotAvailable` if there are none.

    When ``drop_qc`` is True, human QC resolutions are applied to the rows so a
    resolved exception actually flows into the calculation (test-of-twos
    reassignment / scraggly-period drop). Calc reads pass ``drop_qc=True``;
    the ingestion QC detector uses the full rows so a resolved exception still
    lists with its status.

    ``account_id`` scopes to one tenant; None keeps the configured default.
    """
    rows = load_pay_periods(account_id)
    if not rows:
        if account_id is not None:
            raise NoPayrollForClient(f"No payroll for client {account_id} in the active data source.")
        raise PayrollDatasetNotGenerated(NOT_GENERATED_DETAIL)
    return apply_calc_drops(rows) if drop_qc else rows


def row_state(row: dict[str, Any]) -> str:
    """Re-exported from `domain.calculation.headcount`.

    How a row's state is determined is a domain rule — it decides which statute
    applies — so the definition lives there. Kept here because many callers
    already import it from this module.
    """
    return _row_state(row)


def states_present(rows: list[dict[str, Any]]) -> list[str]:
    """Every work state appearing in these rows, sorted."""
    return _states_present(rows)


def unauthored_state_years(
    tax_years: Iterable[int],
    *,
    state: str | None = None,
) -> dict[int, dict[str, str]]:
    """Which `(tax year, state)` pairs have no authored statute.

    A multi-year sweep derives its years from the payroll it was given, and that
    payroll routinely runs past the last year a legislature has published. This
    reports those gaps so a caller can present them as **declined**, which is the
    honest middle ground between failing the whole report and quietly omitting a
    year so the output merely *looks* complete.
    """
    from tools.credit_math import STATE_TO_PACK, load_pack_one_zero

    states = [state.upper()] if state else sorted(STATE_TO_PACK.keys())
    gaps: dict[int, dict[str, str]] = {}
    for year in tax_years:
        for st in states:
            try:
                load_pack_one_zero(st, tax_year=year)
            except FileNotFoundError as exc:
                gaps.setdefault(year, {})[st] = str(exc)
    return gaps


def _pack_for(st: str, tax_year: int, on_unauthored: str) -> Any:
    """The state's One/Zero pack, or None to skip it (an unauthored year under `skip`)."""
    from tools.credit_math import load_pack_one_zero

    try:
        return load_pack_one_zero(st, tax_year=tax_year)
    except FileNotFoundError:
        if on_unauthored == "raise":
            raise
        return None


def iter_state_packs(
    rows: list[dict[str, Any]],
    *,
    tax_year: int,
    state: str | None = None,
    on_unauthored: str = "raise",
) -> Iterator[tuple[str, Any, list[dict[str, Any]]]]:
    """Yield ``(state_code, OneZeroPack, state_rows)`` for each rule pack that has
    rows in ``rows``.

    Skips states with no `one_zero` block (pack is None) and states with no
    matching worksite rows. The state of a row is resolved by `row_state`,
    which prefers an explicit `Work_State` and falls back to the `Worksite_ID`
    prefix — one reading, so a row cannot be visible to one caller and invisible
    to another.

    `on_unauthored` decides what happens when a state has no rule pack for
    `tax_year` [ADR-005]:

    - ``"raise"`` (default) — the caller named this year, so answering under a
      different year's statute would be wrong and silence would be worse.
    - ``"skip"`` — the caller is sweeping a range it derived from data. Yield
      nothing for that state and let the caller report it; pair with
      `unauthored_state_years` so the omission is disclosed rather than hidden.
    """
    from tools.credit_math import STATE_TO_PACK

    if on_unauthored not in ("raise", "skip"):
        raise ValueError("on_unauthored must be 'raise' or 'skip'")

    states = [state.upper()] if state else sorted(STATE_TO_PACK.keys())
    for st in states:
        pack = _pack_for(st, tax_year, on_unauthored)
        if pack is None:
            continue
        state_rows = [r for r in rows if row_state(r) == st]
        if state_rows:
            yield st, pack, state_rows
