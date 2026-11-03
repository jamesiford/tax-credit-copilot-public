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

Two token shapes are accepted and they never mix. A delegated token (a person)
needs the scope and `TCC.User`. An app-only token (the channel gateway) has no
scope and needs `TCC.Agent`; the person it acts for arrives in a header the
API layer parses, because the token cannot carry them. A token with both shapes
is refused.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterable

import jwt

from application.identity import PRINCIPAL_AGENT, PRINCIPAL_USER, Principal

REQUIRED_SCOPE = "user_impersonation"
REQUIRED_ROLE = "TCC.User"
#: The app role the channel gateway's service principal holds. Never a person's.
AGENT_ROLE = "TCC.Agent"

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
        claims = self._claims(token)
        scopes = tuple(str(claims.get("scp", "")).split())
        roles = tuple(_strings(claims.get("roles")))
        shape = _shape(claims, scopes)
        if shape == "agent":
            self._require_agent(scopes, roles)
        else:
            self._require_user(scopes, roles)
        return Principal(
            oid=claims.get("oid"),
            upn=claims.get("preferred_username") or claims.get("upn"),
            name=claims.get("name"),
            tenant_id=claims.get("tid"),
            roles=roles,
            scopes=scopes,
            authenticated=True,
            principal_type=PRINCIPAL_AGENT if shape == "agent" else PRINCIPAL_USER,
        )

    def claims(self, token: str | None) -> dict[str, Any]:
        """The verified claims of a token: signature, issuer, audience and dates checked.

        Public so a second app (the channel gateway) can reuse the same JWKS and
        issuer handling with its own audience and its own rules about roles.
        """
        return self._claims(token)

    def _claims(self, token: str | None) -> dict[str, Any]:
        if not token:
            raise AuthenticationFailed("no bearer token")
        try:
            signing_key = self._keys().get_signing_key_from_jwt(token)
            key = getattr(signing_key, "key", signing_key)
            return jwt.decode(
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

    def _require_user(self, scopes: tuple[str, ...], roles: tuple[str, ...]) -> None:
        if AGENT_ROLE in roles:
            raise AuthorizationFailed(f"a delegated token must not carry the '{AGENT_ROLE}' role")
        if self.required_scope not in scopes:
            raise AuthorizationFailed(f"token lacks the '{self.required_scope}' scope")
        if self.required_role not in roles:
            raise AuthorizationFailed(f"token lacks the '{self.required_role}' app role")

    def _require_agent(self, scopes: tuple[str, ...], roles: tuple[str, ...]) -> None:
        if scopes:
            raise AuthorizationFailed("an app-only token must not carry delegated scopes")
        if self.required_role in roles:
            raise AuthorizationFailed(f"an app-only token must not carry the '{self.required_role}' role")
        if AGENT_ROLE not in roles:
            raise AuthorizationFailed(f"token lacks the '{AGENT_ROLE}' app role")


def _shape(claims: dict[str, Any], scopes: tuple[str, ...]) -> str:
    """`agent` for an app-only token, `user` for a delegated one.

    An app-only v2 token has no `scp` and either `idtyp=app` or a subject equal
    to its object id with no user name. A token that shows both shapes is
    refused: guessing which a half-and-half token means is how a service
    acquires a person's rights.
    """
    named = bool(claims.get("preferred_username") or claims.get("upn") or claims.get("name"))
    app_like = claims.get("idtyp") == "app" or (
        bool(claims.get("oid")) and claims.get("oid") == claims.get("sub") and not named
    )
    if app_like and scopes:
        raise AuthorizationFailed("token mixes app-only and delegated claims")
    if claims.get("idtyp") == "app" and named:
        raise AuthorizationFailed("token mixes app-only and delegated claims")
    return "agent" if app_like else "user"


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []
