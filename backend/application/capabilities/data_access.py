"""What the three data tools share: the service, the channel rule and the failures. [CH-16d]

Kept apart from the tools so each is small and so the one rule that decides who may be handed
person-level rows is written once, where it can be read and tested.

**Who may carry employee-level results.** A result whose rows describe individual employees is
delivered to the person who asked. In Teams and Copilot Chat the platform renders those rows
itself and the model is shown names only. Copilot Cowork is different: it composes its own
answer, so the text a tool returns IS what its model reads, and there is no way to keep a row
from a model that is shown the text. Such a result is therefore refused unless the caller is a
writer (an entitlement the platform already holds per person), and says so plainly. An
aggregate over employee-level data, which carries no person, is allowed everywhere [ADR-009].

**The test is positive, so it fails closed [RM-02].** A caller is trusted with rows only when it
is positively a first-party channel: an agent principal (the gateway, holding the agent role)
acting for a person whose channel is `teams` or `m365-copilot`, asserted by the channel. Anything
else (`cowork`, `api-test`, an unknown or missing channel, a person's own token sent straight to
the API) is treated as Cowork-like. The check lives here, in the API, and does not depend on the
gateway having made it: `invoke` repeats it on every result.
"""
from __future__ import annotations

from typing import Any

from application.capabilities.envelope import AUDIENCE_BOTH, ToolResult
from application.capabilities.errors import DataQueryRefused
from application.capabilities.lanes import EMPLOYEE_LEVEL_CODE, EMPLOYEE_LEVEL_MESSAGE
from application.data.classify import USER
from application.data.errors import QueryError
from application.data.exec_errors import QueryBudgetExceeded
from application.identity import Principal

#: Status and retryability by the query error's stable code; anything else is the caller's to fix (422).
_STATUS: dict[str, tuple[int, bool]] = {
    "query_timeout": (504, True),
    "query_budget_exceeded": (429, True),
    "query_busy": (503, True),
    "data_source_unavailable": (503, False),
    "data_source_disabled": (503, False),
    "query_failed": (502, True),
    "not_read_only": (500, False),
}


def service() -> Any:
    """The process's data-query service. Imported on use: the composition module pulls the adapters."""
    from application.services import get_data_query_service

    return get_data_query_service()


def asker(principal: Principal) -> str:
    """Who a query's budget is spent against: the person, never the gateway that carries them."""
    return principal.effective_oid or principal.actor


def refused(exc: QueryError) -> DataQueryRefused:
    """A query error as the refusal the wire carries, with its field and any wait the caller can act on."""
    status, retryable = _STATUS.get(exc.code, (422, False))
    extra: dict[str, Any] = {} if exc.field is None else {"field": exc.field}
    if isinstance(exc, QueryBudgetExceeded):
        extra["retry_after_seconds"] = exc.retry_after_s
    return DataQueryRefused(exc.message, code=exc.code, status=status, retryable=retryable, extra=extra)


def is_first_party(principal: Principal) -> bool:
    """Positively a first-party channel: the gateway acting for a person whose Teams or Copilot Chat message it asserts.

    Every part is required. A person's own token carries no channel assertion (it is `delegated`, and a header
    from a user principal is ignored at the API edge), and an agent that names no channel, an unknown one,
    `cowork` or `api-test`, or claims a delegated assurance, is not one. [RM-02]
    """
    acting = principal.acting_for if principal.is_agent else None
    return acting is not None and acting.is_first_party


def is_cowork(principal: Principal) -> bool:
    """Whether the caller's model reads whatever text a tool returns: anything not positively first-party.

    Named for Copilot Cowork, the case it exists for; it is true for every caller that is not Teams or Copilot
    Chat, so an unrecognised caller fails closed instead of being given rows.
    """
    return not is_first_party(principal)


def _is_writer(principal: Principal) -> bool:
    from application.services import get_writer_entitlement

    oid = principal.effective_oid
    return bool(oid) and bool(get_writer_entitlement().is_writer(oid))


def refuse_employee_level_beyond_first_party(principal: Principal, audience: str) -> None:
    """Raise the plain refusal when person-level rows were asked for by a caller that is not first-party or a writer."""
    if audience == USER and is_cowork(principal) and not _is_writer(principal):
        raise DataQueryRefused(EMPLOYEE_LEVEL_MESSAGE, code=EMPLOYEE_LEVEL_CODE, status=403)


def refuse_user_lane(principal: Principal, result: ToolResult) -> None:
    """The second API-side wall: a finished result carrying a person-only lane never leaves for such a caller.

    `invoke` calls this on every result, so a capability that forgets the pre-run check (or a future one)
    cannot hand employee rows to a model-reading caller, and the rule does not rest on the gateway's copy.
    Anything not recognisably `both` counts as person-only, the same reading `lanes.py` gives the wire form.
    """
    person_only = bool(result.user_only_facts) or any(b.audience != AUDIENCE_BOTH for b in result.blocks)
    if person_only and is_cowork(principal) and not _is_writer(principal):
        raise DataQueryRefused(EMPLOYEE_LEVEL_MESSAGE, code=EMPLOYEE_LEVEL_CODE, status=403)


def suppress_small_groups(principal: Principal) -> bool:
    """Whether the minimum group size applies: to everybody except a writer, in every channel and both lanes.

    A writer is entitled to the client's employee rows, so a small group tells them nothing they may not
    read. The client check ran at the API edge (`authorize_clients`) before any capability, and this build
    has no per-client ownership beyond it, so "a writer viewing their own client" is a writer on an
    authorised client. An unknown or anonymous caller is not a writer: suppressed. [RM-01, ADR-009]
    """
    return not _is_writer(principal)
