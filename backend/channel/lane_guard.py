"""The gateway's half of the Copilot Cowork rule for employee-level results. [CH-16d, ADR-009]

The API refuses to RUN a query that would list individual employees for Cowork unless the caller
is a writer (`capabilities/data_access.py`). This is the second check, on what comes back: if any
result reaches the gateway carrying a person-only lane (a block marked `user`, or `user_only_facts`)
for a Cowork caller who is not a writer, it is replaced by the same refusal and never forwarded.
Cowork composes its own answer from the text a tool returns, so whatever is in that text IS what
its model reads; a rule enforced in one place only would be one bug from a leak.

Teams and Copilot Chat are not touched: there the orchestrator renders the person's rows itself
and shows its model names only.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from application.capabilities.lanes import EMPLOYEE_LEVEL_CODE, EMPLOYEE_LEVEL_MESSAGE, has_user_lane
from channel.auth import Caller

COWORK = "cowork"


async def blocks_employee_level(
    caller: Caller, body: Mapping[str, Any], is_writer: Callable[[str], Awaitable[bool]],
) -> bool:
    """True when `body` carries person-level rows and this Cowork caller may not be handed them."""
    return caller.acting.channel == COWORK and has_user_lane(body) and not await is_writer(caller.acting.oid)


def refusal() -> tuple[int, dict[str, Any]]:
    """The status and error body that replace the result."""
    return 403, {"error": {"code": EMPLOYEE_LEVEL_CODE, "message": EMPLOYEE_LEVEL_MESSAGE, "retryable": False}}
