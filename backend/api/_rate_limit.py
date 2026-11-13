"""The rate-limit dependency for the routes that write or compute on request. [F07.3]

A route declares `dependencies=[Depends(rate_limited("draft_save"))]`; the policy lives in `application/request_limits.py`.
A refusal is a 429 with `Retry-After`, a code and a remedy, like the other refusals of these routes.
"""
from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request

from api.auth import current_principal
from application import request_limits


def rate_limited(kind: str) -> Callable[[Request], None]:
    """A dependency that counts this caller's request of `kind` and refuses it past the per-minute limit."""

    def check(request: Request) -> None:
        wait = request_limits.seconds_to_wait(kind, current_principal(request))
        if wait:
            raise HTTPException(
                status_code=429, headers={"Retry-After": str(wait)},
                detail={"code": "rate_limited", "reason": f"Too many {kind.replace('_', ' ')} requests from this caller.",
                        "remedy": f"Wait {wait} seconds and try again (RATE_LIMIT_PER_MINUTE)."},
            )

    return check
