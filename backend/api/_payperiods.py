"""Shared pay-period loading + per-state-pack iteration for the One/Zero routers.

Extracted from the former monolithic `api/eligibility.py` so the four One/Zero
endpoints (onezero, retroactive scan, performance, monthly alerts) stop
copy-pasting the same load → 503 → per-state-pack loop. DRY: one source of
truth for "give me the pay-period rows and walk the rule packs".
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Iterable, Iterator

from fastapi import HTTPException

from domain.calculation.headcount import row_state as _row_state
from domain.calculation.headcount import states_present as _states_present
from infrastructure.payroll.pay_period_source import (
    configured_account_id as _configured_account_id,
)
from infrastructure.payroll.pay_period_source import (
    load_pay_periods as _load_pay_periods,
)
from infrastructure.payroll.pay_period_source import (
    load_portfolio_pay_periods as _load_portfolio_pay_periods,
)

_PAY_PERIODS_CSV = Path(__file__).resolve().parent.parent / "data" / "payroll_pay_periods.csv"

_NOT_GENERATED_DETAIL = (
    "Pay-period dataset not generated. Run `python data/generate_pay_periods.py`."
)


# Physical payroll access moved to infrastructure/payroll/. These names are
# re-exported because many callers import them from here, but the single
# implementation lives one layer in - `tools/portfolio.py` previously had to
# import from `api/` to read payroll, which is a dependency pointing the
# wrong way and an import cycle waiting for the right entry point.
configured_account_id = _configured_account_id
load_pay_periods = _load_pay_periods
load_portfolio_pay_periods = _load_portfolio_pay_periods


def require_pay_periods(*, drop_qc: bool = False, account_id: int | None = None) -> list[dict[str, Any]]:
    """Load the pay-period rows or raise the standard 503 if the dataset is missing.

    When ``drop_qc`` is True, human QC resolutions are applied to the rows so a
    resolved exception actually flows into the calculation (test-of-twos
    reassignment / scraggly-period drop). Calc endpoints pass ``drop_qc=True``;
    the ingestion QC detector uses the full rows so a resolved exception still
    lists with its status.

    ``account_id`` scopes to one tenant; None keeps the configured default.
    """
    rows = load_pay_periods(account_id)
    if not rows:
        if account_id is not None:
            # A named tenant with no rows is a different fact from an absent
            # dataset, and telling the caller to go generate fixtures when they
            # asked for client 42 sends them somewhere useless.
            raise HTTPException(
                status_code=404,
                detail=f"No payroll for client {account_id} in the active data source.",
            )
        raise HTTPException(status_code=503, detail=_NOT_GENERATED_DETAIL)
    if drop_qc:
        from api.ingestion import apply_calc_drops  # lazy: avoid import cycle
        rows = apply_calc_drops(rows)
    return rows


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
    from tools.credit_math import STATE_TO_PACK, load_pack_one_zero

    if on_unauthored not in ("raise", "skip"):
        raise ValueError("on_unauthored must be 'raise' or 'skip'")

    states = [state.upper()] if state else sorted(STATE_TO_PACK.keys())
    for st in states:
        try:
            pack = load_pack_one_zero(st, tax_year=tax_year)
        except FileNotFoundError:
            if on_unauthored == "raise":
                raise
            continue
        if pack is None:
            continue
        state_rows = [r for r in rows if row_state(r) == st]
        if not state_rows:
            continue
        yield st, pack, state_rows
