"""Identity, composed: the client authorizer and the Entra token validator. [AUTH-3, D24]

Split out of `bootstrap.wiring`, which re-exports every name here, to keep that module
to the bindings the mediator needs.
"""
from __future__ import annotations

from typing import Any

_client_authorizer: Any | None = None
_token_validator: Any | None = None


def get_client_authorizer() -> Any:
    """The `ClientAuthorizer` port. v2: every `TCC.User` sees every client (D24)."""
    global _client_authorizer
    if _client_authorizer is None:
        from application.identity import AllClientsAuthorizer

        _client_authorizer = AllClientsAuthorizer()
    return _client_authorizer


def set_client_authorizer(authorizer: Any) -> None:
    """Swap the entitlement policy. Used by tests to prove the deny path."""
    global _client_authorizer
    _client_authorizer = authorizer


def get_token_validator() -> Any:
    """The Entra token validator, built from AUTH_TENANT_ID and API_AUDIENCE."""
    global _token_validator
    if _token_validator is None:
        from application.deployment import api_audience, auth_tenant_id
        from infrastructure.auth.entra import EntraTokenValidator

        _token_validator = EntraTokenValidator(
            tenant_id=auth_tenant_id(), api_audience=api_audience()
        )
    return _token_validator


def set_token_validator(validator: Any) -> None:
    global _token_validator
    _token_validator = validator
