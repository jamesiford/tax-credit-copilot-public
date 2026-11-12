"""Primary Reference Dataset Client workspace APIs.

All routes are loopback-only until Entra authentication and employer binding are
implemented. Do not add a remote bypass: the source contains private payroll.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from application.errors import DependencyUnavailable
from tools.reference_workspace import ReferenceWorkspaceService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["reference-workspace"])
_SERVICE = ReferenceWorkspaceService()
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _require_local(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="Reference Dataset detail is local-only until Entra authentication is enabled.",
        )


def _service() -> ReferenceWorkspaceService:
    return _SERVICE


def _load(*, force: bool = False):
    try:
        return _service().get(force=force)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Reference workspace failed: {exc}") from exc


def _summary_or_unavailable(*, force: bool = False) -> dict[str, Any]:
    """The sealed run's summary, or a statement that it is not available and why.

    The shell renders nothing until this answers, and the sealed run needs the reference client. A
    source that does not hold it must still open the portal on the real book, so that is an answer,
    not an error. A dependency that is down or unconfigured is different: it propagates as a 503 that
    names it (`application.errors`), because nothing can be read at all.
    """
    try:
        _service().get(force=force)
        return _service().summary()
    except DependencyUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - the sealed run is one artifact; its failure, whatever the cause, must not blind the shell
        log.warning("sealed reference run unavailable: %s: %s", type(exc).__name__, str(exc)[:200])
        return {
            "available": False,
            "workspace": None,
            "reason": str(exc)[:400],
            "remedy": "The certified reference run needs the reference client (account 1001) and its source; "
                      "every other view reads the data that is present.",
        }


class SearchRequest(BaseModel):
    q: str = ""
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class EligibilitySearchRequest(SearchRequest):
    status: Literal["all", "both", "min_max_only", "pay_period_only", "neither"] = "all"
    proximity: Literal["all", "near_floor"] = "all"


class EmployeeRequest(BaseModel):
    record_token: str = Field(min_length=8, max_length=128)


class ContributorRequest(BaseModel):
    method: Literal["min_max", "pay_period"]
    unit_id: str
    fein: str
    month_index: int = Field(ge=0, le=11)


class ComparisonStageRequest(BaseModel):
    stage: Literal[
        "common_employee_totals",
        "min_max_eligibility",
        "pay_period_eligibility",
        "min_max_onezero_summary",
        "pay_period_onezero_summary",
    ]


@router.get("")
def workspace_summary(request: Request) -> dict[str, Any]:
    _require_local(request)
    return _summary_or_unavailable()


@router.post("/refresh")
def refresh_workspace(request: Request) -> dict[str, Any]:
    _require_local(request)
    return _summary_or_unavailable(force=True)


@router.post("/source/search")
def search_source(request: Request, payload: SearchRequest) -> dict[str, Any]:
    _require_local(request)
    _load()
    return _service().source_rows(query=payload.q, limit=payload.limit, offset=payload.offset)


@router.post("/eligibility/search")
def search_eligibility(request: Request, payload: EligibilitySearchRequest) -> dict[str, Any]:
    _require_local(request)
    _load()
    return _service().eligibility_rows(
        query=payload.q,
        status=payload.status,
        proximity=payload.proximity,
        limit=payload.limit,
        offset=payload.offset,
    )


@router.post("/employee")
def employee_drill(request: Request, payload: EmployeeRequest) -> dict[str, Any]:
    _require_local(request)
    _load()
    result = _service().employee(payload.record_token)
    if result is None:
        raise HTTPException(status_code=404, detail="employee record not found")
    return result


@router.get("/onezero/{method}")
def onezero_summary(request: Request, method: Literal["min_max", "pay_period"]):
    _require_local(request)
    _load()
    return _service().onezero_summary(method)


@router.post("/onezero/contributors")
def onezero_contributors(request: Request, payload: ContributorRequest) -> dict[str, Any]:
    _require_local(request)
    _load()
    return {
        "run": _service().run_ref(),
        "method": payload.method,
        "unit_id": payload.unit_id,
        "fein": payload.fein,
        "month_index": payload.month_index,
        "contributors": _service().contributors(
            method=payload.method,
            unit_id=payload.unit_id,
            fein=payload.fein,
            month_index=payload.month_index,
        ),
    }


@router.get("/calculation-walk")
def calculation_walk(request: Request) -> dict[str, Any]:
    _require_local(request)
    _load()
    return _service().calculation_walk()


@router.get("/assumptions")
def assumptions(request: Request) -> dict[str, Any]:
    _require_local(request)
    return _service().assumptions()


@router.get("/comparison")
def comparison(request: Request) -> dict[str, Any]:
    _require_local(request)
    state = _load()
    return _service().comparison_summary(state)


@router.post("/comparison/stage")
def comparison_stage(request: Request, payload: ComparisonStageRequest) -> dict[str, Any]:
    _require_local(request)
    _load()
    result = _service().comparison_stage(payload.stage)
    if result is None:
        raise HTTPException(status_code=404, detail="Access outputs or comparison stage not supplied")
    return result
