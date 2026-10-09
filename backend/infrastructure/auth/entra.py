"""Entra ID bearer-token validation. [AUTH-3, D24]

The API trusts a token, never a network position. A token is accepted only if:

- its signature verifies against the tenant's published keys (JWKS, cached),
- it is a v2.0 token from `https://login.microsoftonline.com/<tenant>/v2.0`,
- its audience is the API registration (`API_AUDIENCE`; the `api://` URI and the
  bare client id are both accepted, since v2 tokens carry the client id),
- it is in date.

Those failures are 401: the caller has not proven who they are. Proven but
missing the delegated scope `user_impersonation` or the app role `TCC.User` is
403: they are who they say, and still may not.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterable

import jwt

from application.identity import Principal

REQUIRED_SCOPE = "user_impersonation"
REQUIRED_ROLE = "TCC.User"

#: Accept a token a few seconds either side of the clock it was minted by.
_LEEWAY_S = 60


class AuthenticationFailed(Exception):
    """401: no proof of identity."""


class AuthorizationFailed(Exception):
    """403: identity proven, permission missing."""


def issuer_for(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/v2.0"


def jwks_uri_for(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"


def audiences(api_audience: str) -> list[str]:
    """The accepted `aud` values for one API registration."""
    values = [a.strip() for a in api_audience.split(",") if a.strip()]
    out: list[str] = []
    for value in values:
        out.append(value)
        if value.startswith("api://"):
            out.append(value[len("api://"):])
    return out


@dataclass
class EntraTokenValidator:
    tenant_id: str
    api_audience: str
    required_scope: str = REQUIRED_SCOPE
    required_role: str = REQUIRED_ROLE
    #: Anything with `get_signing_key_from_jwt(token) -> key` (PyJWKClient's
    #: interface). Injected by tests; built lazily otherwise and cached.
    jwks_client: Any = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.api_audience:
            raise ValueError("Entra validation needs a tenant id and an API audience")
        self._lock = threading.Lock()

    def _keys(self) -> Any:
        if self.jwks_client is None:
            with self._lock:
                if self.jwks_client is None:
                    self.jwks_client = jwt.PyJWKClient(
                        jwks_uri_for(self.tenant_id), cache_keys=True, lifespan=3600
                    )
        return self.jwks_client

    def validate(self, token: str | None) -> Principal:
        if not token:
            raise AuthenticationFailed("no bearer token")
        try:
            signing_key = self._keys().get_signing_key_from_jwt(token)
            key = getattr(signing_key, "key", signing_key)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=audiences(self.api_audience),
                issuer=issuer_for(self.tenant_id),
                leeway=_LEEWAY_S,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except Exception as exc:  # noqa: BLE001 - any failure to prove identity is a 401
            raise AuthenticationFailed(f"invalid token: {type(exc).__name__}") from exc

        scopes = tuple(str(claims.get("scp", "")).split())
        roles = tuple(_strings(claims.get("roles")))
        if self.required_scope not in scopes:
            raise AuthorizationFailed(f"token lacks the '{self.required_scope}' scope")
        if self.required_role not in roles:
            raise AuthorizationFailed(f"token lacks the '{self.required_role}' app role")
        return Principal(
            oid=claims.get("oid"),
            upn=claims.get("preferred_username") or claims.get("upn"),
            name=claims.get("name"),
            tenant_id=claims.get("tid"),
            roles=roles,
            scopes=scopes,
            authenticated=True,
        )


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []
