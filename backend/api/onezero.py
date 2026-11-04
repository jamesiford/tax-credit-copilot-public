"""One/Zero statutory engine endpoints.

  GET  /api/onezero/matrix/{tax_year}  — the monthly allocation for one client
  GET  /api/onezero/{tax_year}         — both methods + reconciliation + [H1..I2]
  GET  /api/onezero/{tax_year}/employee/{employee_id} — one employee's derivation
  POST /api/onezero/employee/{employee_id}/review     — human validation annotation
  GET  /api/designations/{state}       — [L2] designation timelines
  GET  /api/reconcile/{tax_year}       — [P1] benchmark reconciliation
  GET  /api/qc/{tax_year}              — [B5] QC exception report

Thin [ADR-003]: every route builds a query or a command and sends it through the
mediator; the statutory Base Calculation lives in `application/queries/` over
`domain.calculation.onezero`. This module translates HTTP to those and their errors
back to status codes.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi import Query as FastAPIQuery
from pydantic import BaseModel, Field

from api._payperiods import payroll_errors_as_http
from api.auth import attributed
from application.commands.review_employee import ReviewEmployeeCommand
from application.onezero_errors import OneZeroNotFound
from application.queries._client_run import ClientRunNotAvailable
from application.queries.get_designation_splits import GetDesignationSplitsQuery
from application.queries.get_employee_derivation import GetEmployeeDerivationQuery
from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery
from application.queries.get_one_zero import GetOneZeroQuery, InvalidOneZeroMethod
from application.queries.get_qc_exception_report import GetQcExceptionReportQuery
from application.queries.get_reconciliation import GetReconciliationQuery
from application.services import get_mediator

router = APIRouter(prefix="/api", tags=["onezero"])


@router.get("/onezero/matrix/{tax_year}")
def onezero_matrix(
    tax_year: int,
    state: str = FastAPIQuery("GA", description="Two-letter state code"),
    account_id: int | None = FastAPIQuery(None, description="Client; defaults to the tenant"),
    method: str = FastAPIQuery("min_max", description="min_max | pay_period"),
) -> dict[str, Any]:
    """The monthly one/zero allocation for one client, at unit x legal entity.

    Thin [ADR-003]: the resolution and the run live in the application layer.
    The older `/onezero/{tax_year}` below buckets rows by a global fiscal-year
    end month; this one resolves the window from the client's own rules, so it
    agrees with `/api/eligibility/{tax_year}` for the same client and year.
    """
    try:
        query = GetOneZeroMatrixQuery(
            tax_year=tax_year, state=state, account_id=account_id, method=method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(query)
    except ClientRunNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/onezero/{tax_year}")
def one_zero(
    tax_year: int,
    state: str | None = None,
    method: str = "both",
    fein: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """Run the statutory One/Zero Base Calculation for a given tax year.

    Query params:
      `state`  (optional): two-letter state code. If omitted, every pack runs.
      `method` (optional): [H5] CALC-01/02 — 'pay_period' | 'min_max' | 'both'.
      `fein`   (optional): [I1] CALC-06 — restrict to a single legal entity.
      `account_id` (optional): which tenant to calculate. Omitted keeps the
        configured default, so existing single-tenant callers are unchanged.
    """
    try:
        query = GetOneZeroQuery(
            tax_year=tax_year, state=state, method=method, fein=fein, account_id=account_id,
        )
    except InvalidOneZeroMethod as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with payroll_errors_as_http():
        return get_mediator().send(query)


class EmployeeReviewRequest(BaseModel):
    """Human validation/correction annotation for one employee's eligibility."""
    status: str = Field("validated", pattern="^(validated|flagged|cleared)$")
    note: str | None = None
    reviewer: str = "Reviewer"


@router.get("/onezero/{tax_year}/employee/{employee_id}")
def one_zero_employee(
    tax_year: int,
    employee_id: str,
    state: str = "GA",
    account_id: int | None = None,
) -> dict[str, Any]:
    """Per-employee derivation drill: source pay-period lines → weekly averages
    → floor test (hours & wages) → weight (1 / pt_weight / 0) → per-month
    contribution → contribution to Average Headcount. A faithful slice of the
    statutory engine — it can never disagree with the headline number.
    """
    query = GetEmployeeDerivationQuery(
        tax_year=tax_year, employee_id=employee_id, state=state, account_id=account_id,
    )
    try:
        with payroll_errors_as_http():
            return get_mediator().send(query)
    except OneZeroNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/onezero/employee/{employee_id}/review")
def review_employee(employee_id: str, req: EmployeeReviewRequest, request: Request) -> dict[str, Any]:
    """Record a human validation/correction annotation for an employee
    (in-memory; resets on restart — prod persists to the audit store)."""
    return get_mediator().send(ReviewEmployeeCommand(
        actor=attributed(request, req.reviewer, default="Reviewer"),
        employee_id=employee_id, status=req.status, note=req.note,
    ))


@router.get("/designations/{state}")
def designations(state: str, tax_year: int = 2025) -> dict[str, Any]:
    """[L2] CALC-08 — designation timelines + parallel-calc flags for a state.
    Surfaces which GA locations changed designation between the base year and
    the analysis year (a change that, combined with net-new jobs, spawns two
    concurrent calcs for the same location).
    """
    return get_mediator().send(GetDesignationSplitsQuery(state=state, tax_year=tax_year))


@router.get("/reconcile/{tax_year}")
def reconcile_endpoint(tax_year: int, account_id: int | None = None) -> dict[str, Any]:
    """[P1] PILOT-04 — reconcile our live engine output against a benchmark.

    Ties our per-state Average Headcount out against a SYNTHETIC benchmark
    fixture standing in for the partner's Access/Copilot calc. The real parallel run
    happens inside the partner's environment (payroll never leaves the partner);
    this proves the reconciliation machinery and surfaces any discrepancies.
    """
    try:
        with payroll_errors_as_http():
            return get_mediator().send(GetReconciliationQuery(tax_year=tax_year, account_id=account_id))
    except OneZeroNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/qc/{tax_year}")
def qc_exception_report(
    tax_year: int,
    state: str | None = None,
    min_wages: float = 50.0,
    min_hours: float = 4.0,
    account_id: int | None = None,
) -> dict[str, Any]:
    """[B5 / CALC-07 + CALC-08 / AI-02] Automated QC exception report.

    Surfaces the "2s" (an employee counted at >1 unit in a month) and scraggly
    low-value pay periods for human review. Nothing is dropped automatically —
    every anomaly is a validation checkpoint.
    """
    with payroll_errors_as_http():
        return get_mediator().send(GetQcExceptionReportQuery(
            tax_year=tax_year, state=state, min_wages=min_wages,
            min_hours=min_hours, account_id=account_id,
        ))
