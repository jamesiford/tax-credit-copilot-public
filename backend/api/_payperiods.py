"""The HTTP edge of payroll loading.

The loading, the per-state-pack iteration and the QC filter live in
`application/payroll_rows`, which raises ordinary errors. This module translates the
two ways there can be no payroll into the status codes callers have always seen (404
for a named client with no rows, 503 for a dataset that was never generated) and
re-exports the rest, because the One/Zero routers and their tests already import them
from here.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException

from application import payroll_rows
from application.payroll_rows import (  # noqa: F401 - re-exported: callers import these from here
    NoPayrollForClient,
    configured_account_id,
    iter_state_packs,
    load_pay_periods,
    load_portfolio_pay_periods,
    row_state,
    states_present,
    unauthored_state_years,
)


@contextmanager
def payroll_errors_as_http() -> Iterator[None]:
    """Map "there is no payroll" onto 404 (a named client) or 503 (no dataset)."""
    try:
        yield
    except NoPayrollForClient as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except payroll_rows.PayrollNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def require_pay_periods(*, drop_qc: bool = False, account_id: int | None = None) -> list[dict[str, Any]]:
    """The pay-period rows, or the standard 404/503 if there are none."""
    with payroll_errors_as_http():
        return payroll_rows.require_pay_periods(drop_qc=drop_qc, account_id=account_id)
