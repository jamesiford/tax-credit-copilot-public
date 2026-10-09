"""Authentication and client authorization at the API edge. [AUTH-3, AUTH-4, AUTH-5, D24]

One app-level dependency, `request_guard`, runs before every route:

1. **Who is asking.** Under `AUTH_MODE=entra` the bearer token is validated
   (401 without proof, 403 without the scope or role). Under `none` the caller
   is `ANONYMOUS` — the mode exists for local and synthetic-data demos, and the
   startup check keeps it away from customer data (D26).
2. **May they see this client.** Every client id the request names — in the
   path, the query string, or the top level of a JSON body (`client_id`,
   `account_id`) — is checked against the `ClientAuthorizer` port. A refusal is
   403, before any handler runs.

Health and readiness probes are exempt: the platform calls them without a token.

`attributed(request, supplied)` is how a write names its author: the token's
identity when there is one, otherwise what the request said, otherwise
`anonymous`. A server never invents a name.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from fastapi import APIRouter, HTTPException, Request

from application.deployment import auth_mode
from application.identity import ANONYMOUS, Principal

router = APIRouter(prefix="/api", tags=["auth"])

#: Called by the platform without credentials.
PUBLIC_PATHS = frozenset({"/api/health", "/api/ready"})

#: Routes that authorize the client THEMSELVES, so a refusal is recorded where it
#: happens: a download writes `artifact_access` = denied. The caller is still
#: authenticated here; only the client check moves into the handler.
SELF_AUTHORIZING = re.compile(r"^/api/clients/\d+/artifacts/[^/]+$")

#: Names a request uses for the client it is about.
_CLIENT_KEYS = ("client_id", "account_id")


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _as_client_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


async def _client_ids(request: Request) -> set[int]:
    found: list[Any] = []
    for key in _CLIENT_KEYS:
        found.append(request.path_params.get(key))
        found.extend(request.query_params.getlist(key))
    if request.method in ("POST", "PUT", "PATCH") and "json" in (request.headers.get("content-type") or ""):
        raw = await request.body()  # cached by Starlette; the handler reads it again
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        if isinstance(body, dict):
            found.extend(body.get(key) for key in _CLIENT_KEYS)
    return {cid for cid in (_as_client_id(v) for v in found) if cid is not None}


def authenticate(request: Request) -> Principal:
    if auth_mode() != "entra":
        return ANONYMOUS
    from application.wiring import get_token_validator
    from infrastructure.auth.entra import AuthenticationFailed, AuthorizationFailed

    try:
        return get_token_validator().validate(_bearer(request))
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    except AuthorizationFailed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def authorize_clients(principal: Principal, client_ids: Iterable[int]) -> None:
    from application.wiring import get_client_authorizer

    authorizer = get_client_authorizer()
    for client_id in sorted(client_ids):
        if not authorizer.is_authorized(principal, client_id):
            raise HTTPException(status_code=403, detail=f"not authorized for client {client_id}")


async def request_guard(request: Request) -> None:
    """App-level dependency: authenticate, then authorize every named client."""
    if request.url.path in PUBLIC_PATHS:
        return
    principal = authenticate(request)
    request.state.principal = principal
    if SELF_AUTHORIZING.match(request.url.path):
        return
    authorize_clients(principal, await _client_ids(request))


def current_principal(request: Request | None) -> Principal:
    if request is None:  # a route function called directly, outside a request
        return ANONYMOUS
    return getattr(request.state, "principal", None) or ANONYMOUS


def attributed(request: Request | None, supplied: str | None = None, *, default: str = "anonymous") -> str:
    """The author of a write: the token's identity, else the request's claim, else `default`."""
    principal = current_principal(request)
    if principal.authenticated:
        return principal.actor
    return (supplied or "").strip() or default


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    """Who the API believes the caller is. The frontend attributes decisions from this."""
    return {"auth_mode": auth_mode(), **current_principal(request).to_dict()}
