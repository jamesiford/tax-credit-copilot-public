"""`GET /api/audit/channel` — what one person did through the channel. [CH-03]

Thin: parse, dispatch, shape. Readable by a normal signed-in human (`TCC.User`,
enforced by the app-level guard); the trail is not a place a channel agent
should read its own history.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.auth import current_principal
from application.queries.get_channel_audit import MAX_LIMIT, GetChannelAuditQuery
from application.wiring import get_mediator

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/channel")
def channel_audit(
    request: Request,
    user_oid: str = Query(..., min_length=1, description="Entra object id of the user"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    tool: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    """Events newest first, plus one collapsed entry per request (`pending` if it never ended)."""
    if current_principal(request).is_agent:
        raise HTTPException(status_code=403, detail="the channel agent may not read the channel audit trail")
    try:
        return get_mediator().send(
            GetChannelAuditQuery(user_oid=user_oid, since=since, until=until, tool=tool, limit=limit)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
