"""The scope dimension: which clients, which programs, which years.

Scope is **persistent and orthogonal**, not a view: every calculating screen renders at
some point in `client x program x year`, and the operator moves through that space
rather than navigating to a different page to change client. Year is first-class because
statute is year-scoped [ADR-005].

Thin [ADR-003]: both reads are queries in `application/queries/get_scope`. This module
maps the three ways a client's scope cannot be established onto status codes.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from application import client_book
from application.queries.get_scope import (
    GetClientScopeQuery,
    GetScopeOptionsQuery,
    NoPayrollForScope,
    NoResolvableWorkState,
    UnknownClient,
)
from application.services import get_mediator

router = APIRouter(prefix="/api/scope", tags=["scope"])

# The client book and the programme catalogue moved to `application/client_book`
# so a caller that is not a router can read them. The underscore names stay
# because `summary` already imports them from here.
_is_placeholder_year = client_book.is_placeholder_year
_programs = client_book.programs
_clients = client_book.clients
_accounts_from_warehouse = client_book.accounts_from_warehouse


@router.get("")
def scope_options() -> dict[str, Any]:
    """Everything needed to render the scope selector, in one round trip."""
    return get_mediator().send(GetScopeOptionsQuery())


@router.get("/client/{account_id}")
def client_scope(account_id: int) -> dict[str, Any]:
    """What one client's data actually supports.

    The years here come from the client's PAYROLL, and are intersected with the
    years the programs can be priced for. Those two sets are routinely different
    — payroll runs past the last published wage table — and the difference is
    reported rather than hidden, because "we hold your 2026 payroll but cannot
    price it yet" is a real answer.
    """
    try:
        return get_mediator().send(GetClientScopeQuery(account_id=account_id))
    except (UnknownClient, NoPayrollForScope) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoResolvableWorkState as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
