"""The Copilot summary at the top of each page: headlines, streamed, and checked.

Thin [ADR-003]. The page's figures are read through the SAME endpoint functions
the page itself calls, so the summary describes the answer on screen and not a
second one. `tools/page_brief.py` shapes them into a brief; `PageSummaryAgent`
narrates it [ADR-004]; `unsupported_figures` checks what it said.

Opened on demand, never on page load: a narration costs ~10 seconds and a
Foundry call, and most readers only want the grid.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.chat import _TELEMETRY_CONTEXT, _sse, _stream_agent

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["summary"])

AGENT = "PageSummaryAgent"


class SummaryRequest(BaseModel):
    """Which page, and the scope that page was rendered under."""

    page: Literal["portfolio", "client", "unit", "employee"]
    client_id: int | None = None
    tax_year: int | None = None
    state: str = "GA"
    method: str = Field("min_max", pattern="^(min_max|pay_period)$")
    worksite_id: str | None = Field(default=None, max_length=64)
    month: int | None = Field(default=None, ge=1, le=12)
    #: The employee page's handle. Never an employee id.
    record_token: str | None = Field(default=None, min_length=8, max_length=128)


def _client_name(client_id: int | None) -> str:
    from api.scope import _clients

    for client in _clients():
        if client_id is not None and int(client["account_id"]) == int(client_id):
            return str(client.get("name") or f"Account {client_id}")
    return f"Account {client_id}"


def _placeholder(state: str, year: int | None) -> bool:
    from api.scope import _is_placeholder_year
    from api.trend import _program_code_for_state

    program = _program_code_for_state(state)
    return bool(program and year and _is_placeholder_year(program, int(year)))


def build_brief(req: SummaryRequest) -> dict[str, Any]:
    """The page's own payload, shaped into a brief. Raises HTTPException as the page would."""
    from tools import page_brief

    state = req.state.upper()
    if req.page == "portfolio":
        from api.claims import portfolio_v2

        book = portfolio_v2(
            year=None, program=None, outcome=None, scope=None, near=None, status=None,
            sort="priority", order="asc", limit=200, offset=0,
        )
        return page_brief.portfolio_brief(book)

    if req.client_id is None:
        raise HTTPException(status_code=422, detail=f"a {req.page} summary needs client_id")
    name = _client_name(req.client_id)

    if req.page == "client":
        from api.scope import _programs
        from api.trend import _program_code_for_state, v2_client_units

        payload = v2_client_units(
            req.client_id, year=None, state=state, method=req.method, limit=5000, offset=0,
        )
        program = _program_code_for_state(state)
        placeholder = next(
            (p.get("placeholder_years") or [] for p in _programs() if p["program_code"] == program), [],
        )
        return page_brief.client_brief(payload, client_name=name, placeholder_years=placeholder)

    if req.tax_year is None:
        raise HTTPException(status_code=422, detail=f"a {req.page} summary needs tax_year")

    if req.page == "unit":
        from api.trend import v2_client_unit_detail

        if not req.worksite_id:
            raise HTTPException(status_code=422, detail="a unit summary needs worksite_id")
        payload = v2_client_unit_detail(
            req.client_id, req.worksite_id, year=req.tax_year, month=req.month, state=state,
            method=req.method, sort="avg_weekly_hours", order="desc", near_min_hours=None,
            limit=None, filter=None, near_filter=None,
        )
        return page_brief.unit_brief(
            payload, client_name=name, month=req.month,
            placeholder=_placeholder(state, req.tax_year),
        )

    from api.trend import EmployeeDrillRequest, employee_drill

    if not req.record_token:
        raise HTTPException(status_code=422, detail="an employee summary needs record_token")
    drill = employee_drill(EmployeeDrillRequest(
        record_token=req.record_token, tax_year=req.tax_year, state=state,
        account_id=req.client_id,
    ))
    return page_brief.employee_brief(drill, placeholder=_placeholder(state, req.tax_year))


def _token_text(frame: str) -> str:
    """The prose one SSE `token` frame carries, or ''."""
    if not frame.startswith("event: token"):
        return ""
    try:
        return json.loads(frame.split("data: ", 1)[1]).get("content", "")
    except (IndexError, ValueError):
        return ""


async def _stream(app: Any, req: SummaryRequest) -> AsyncIterator[str]:
    from tools.page_brief import unsupported_figures

    try:
        brief = await asyncio.to_thread(build_brief, req)
    except HTTPException as exc:
        yield _sse("error", {"detail": exc.detail})
        yield _sse("done", {})
        return
    except Exception as exc:  # noqa: BLE001 - the page stands without its summary
        log.exception("page brief failed")
        yield _sse("error", {"detail": f"The figures for this summary could not be read: {exc}"})
        yield _sse("done", {})
        return

    yield _sse("brief", {"page": brief["page"], "headline": brief["headline"], "caveats": brief["caveats"]})

    registry = getattr(app.state, "registry", None)
    if registry is None or AGENT not in getattr(registry, "by_name", {}):
        # No model: say the computed facts rather than nothing. They are the
        # brief itself, so there is nothing to check.
        yield _sse("fallback", {"facts": brief["facts"], "note": "Copilot is not connected; these are the computed facts."})
        yield _sse("done", {})
        return

    ctx = _TELEMETRY_CONTEXT.set({"app": app, "request_id": str(uuid.uuid4()), "intent": f"summary:{req.page}"})
    text = []
    try:
        prompt = (
            f"Summarise the {brief['page']} page for {brief['subject']}.\n\n"
            f"JSON:\n{json.dumps(brief, indent=2, default=str)}"
        )
        async for frame in _stream_agent(AGENT, registry[AGENT].agent, prompt):
            text.append(_token_text(frame))
            yield frame
    finally:
        _TELEMETRY_CONTEXT.reset(ctx)

    written = "".join(text)
    if f"[{AGENT} failed" in written:
        yield _sse("fallback", {"facts": brief["facts"], "note": "Copilot could not answer; these are the computed facts."})
    else:
        yield _sse("check", {"unsupported": unsupported_figures(written, brief)})
    yield _sse("done", {})


@router.post("/summary")
async def page_summary(req: SummaryRequest, request: Request) -> StreamingResponse:
    """Stream the headlines of one page, then say whether every figure checked out."""
    return StreamingResponse(
        _stream(request.app, req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
