"""`GET /api/capabilities` and `POST /api/capabilities/{tool}` — the tools, over HTTP. [CH-06, ADR-003]

Thin: parse, dispatch, shape. Every capability runs here, inside the API process,
because this is where the Gold reads and sealed runs are warm; the channel gateway
and anything else that wants a tool calls this rather than importing it.

The caller is whoever the app-level guard authenticated: a person (`TCC.User`) or
the gateway (`TCC.Agent`, naming the person it acts for). A write enforces its
writer entitlement in the capability, so nothing a caller claims can skip it.
A call that runs past `CAPABILITY_TIMEOUT_SECONDS` returns a structured `timeout`
and does not hang the caller; a timed-out COMMIT may still land, which is why a
retry carries the same idempotency key and replays rather than repeats.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.auth import current_principal
from application.capabilities import catalog
from application.capabilities.invoke import (
    CapabilityFailure, client_ids, failure_for, invoke, merge_commit_arguments, resolve, timeout_seconds,
)
from application.identity import Principal

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


class CapabilityCall(BaseModel):
    """A tool call. The catalog schema validates `args`; the other two serve commits."""

    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)
    confirmation_token: str | None = Field(default=None, max_length=500)


def _refuse_unentitled_clients(principal: Principal, ids: set[int]) -> None:
    from application.wiring import get_client_authorizer

    authorizer = get_client_authorizer()
    for client_id in sorted(ids):
        if not authorizer.is_authorized(principal, client_id):
            raise CapabilityFailure(403, "not_authorized", f"not authorized for client {client_id}")


def _error(failure: CapabilityFailure) -> JSONResponse:
    return JSONResponse(status_code=failure.status, content=failure.body())


@router.get("")
def list_capabilities() -> dict[str, Any]:
    """The catalog a channel caller may use: names, kinds, schemas and whether each is built."""
    return {"tools": [spec.to_dict() for spec in catalog.offered_or_declared()]}


@router.post("/{tool}")
async def run_capability(tool: str, call: CapabilityCall, request: Request) -> Any:
    """Run one capability for the authenticated caller and return its envelope."""
    principal = current_principal(request)
    try:
        spec = resolve(tool)
        args = merge_commit_arguments(
            spec, call.args, idempotency_key=call.idempotency_key, confirmation_token=call.confirmation_token,
        )
        _refuse_unentitled_clients(principal, client_ids(args))
        result = await asyncio.wait_for(asyncio.to_thread(invoke, tool, args, principal), timeout_seconds())
    except asyncio.TimeoutError:
        return _error(CapabilityFailure(504, "timeout", f"{tool} did not finish in time", retryable=True))
    except Exception as exc:  # noqa: BLE001 - invoke raises CapabilityFailure; anything else is mapped the same way
        return _error(failure_for(exc))
    return result.to_dict()
