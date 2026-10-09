"""The One/Zero monthly matrix, for a given client, programme and tax year.

The sealed workspace could already show this, but only ever for the certified
reference run: `tools/reference_onezero.py` builds its matrix on top of a
`ReferenceStep1Run`, which exists for exactly one client. This query runs the
same shape over the production engine, so any client can be asked.

What it deliberately does NOT claim:

- **No rounding triple.** The sealed view carries full-precision, source-rounded
  and application-rounded averages side by side because they exist to reconcile
  against the partner's Access output. There is no Access output for any other
  client, so presenting three columns here would be three decimal places of
  false precision.
- **No test-of-twos disposition list.** `_dedupe_one_per_month` in the production
  engine resolves an employee appearing at two units in one month — most recent
  unit wins — and `flags` records every candidate it resolved. What it does not
  record is which segment survived, so the count of contested months is
  evidenced here while the reference path's per-flag "kept segment / decision
  basis" columns are not available.

The matrix rides along in the response rather than sitting behind a second
endpoint. It is one row per (eligible employee, unit, segment) — 825 rows for
the reference client's 539 eligible employees — so shipping it costs less than
re-running the engine on every drill-in.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.queries._client_run import ClientRunNotAvailable

_METHODS = ("min_max", "pay_period")


@dataclass(frozen=True)
class GetOneZeroMatrixQuery(Query):
    """The One/Zero monthly matrix for one client-programme-year."""

    tax_year: int
    state: str
    account_id: int | None = None
    method: str = "min_max"

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise ValueError(f"method must be one of {_METHODS}, got {self.method!r}")


_MONTH_KEYS = tuple(f"month_{index:02d}" for index in range(1, 13))


def handle_get_onezero_matrix(query: GetOneZeroMatrixQuery) -> dict[str, Any]:
    """The One/Zero allocation, read from the run that produced it.

    This replayed a certified method over the client's whole payroll on every
    page load. The allocation was already in `onezero_matrix`, and the four
    run-level figures the screen states — annual average, eligible count, matrix
    rows and contested months — are in `run_method_summary`, which exists
    because the deduped matrix cannot show that a contest happened.
    """
    import json

    from application.queries._client_run import resolve_statute
    from application.wiring import get_gold_reader

    if query.account_id is None:
        raise ClientRunNotAvailable(
            "a One/Zero matrix is a fact about one client; select one"
        )

    resolved = resolve_statute(
        account_id=query.account_id, state=query.state, tax_year=query.tax_year
    )

    reader = get_gold_reader()
    with reader.scope():
        read = reader.onezero_matrix(
            query.account_id, tax_year=query.tax_year, method=query.method
        )

    base = {
        "account_id": query.account_id,
        "state": resolved.state,
        "program_code": resolved.program_code,
        "tax_year": query.tax_year,
        "method": query.method,
        "thresholds": resolved.floors.as_dict(),
        "fiscal": resolved.window.as_dict(),
    }

    summary = read["summary"]
    if summary is None:
        return {
            **base,
            "calculation_state": "not_calculated",
            "message": (
                f"TY{query.tax_year} has not been calculated for this client. "
                f"It carries no figure — not a zero."
            ),
            "run": read["run"],
            "months": [], "units": 0, "matrix_rows": 0,
            "eligible_employees": 0, "annual_average": 0.0,
            "summary": [], "matrix": [], "flags": [], "contested_months": 0,
        }

    units = [
        {
            "unit_id": row["worksite_id"],
            "fein": row["entity_fein"],
            "month_totals": [float(row[key] or 0) for key in _MONTH_KEYS],
            "total": float(row["total"] or 0),
            "average_headcount": float(row["average_headcount"] or 0),
        }
        for row in read["units"]
    ]

    matrix = [
        {
            "record_token": row["record_token"],
            "employee_id": row["employee_id"],
            "unit_id": row["worksite_id"],
            "fein": row["entity_fein"],
            "months": [float(row[key] or 0) for key in _MONTH_KEYS],
            "weight": float(row["weight"] or 1.0),
        }
        for row in read["matrix"]
    ]

    return {
        **base,
        "calculation_state": "calculated",
        "run": read["run"],
        "months": json.loads(summary["month_ends"]),
        "units": int(summary["unit_fein_rows"]),
        "matrix_rows": int(summary["matrix_rows"]),
        "eligible_employees": int(summary["eligible_employees"]),
        "annual_average": float(summary["annual_average"]),
        "summary": units,
        "matrix": matrix,
        # The flag DETAIL is engine state and is not persisted; the count is,
        # because it is the only part the screen states. Naming it as empty
        # beats implying the run recorded nothing to decide.
        "flags": [],
        "contested_months": int(summary["contested_months"]),
    }
