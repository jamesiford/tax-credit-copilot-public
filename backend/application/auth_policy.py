"""How callers sign in, and when running without sign-in is allowed. [AUTH-5, D26, RM-03]

`AUTH_MODE` defaults to `entra`. An environment that forgot to say how callers
authenticate must demand a token; the alternative default served payroll to
anybody who could reach the process. `none` is a local-development opt-in and
it has to be stated twice (`AUTH_MODE=none` and `ENVIRONMENT=local`): an unset
`ENVIRONMENT` means "local" for store defaults, which is right for a clone and
wrong as permission to skip authentication.

The one other route to `none` is a deployed demo of synthetic data (the public
profile): it needs `ALLOW_ANONYMOUS_SYNTHETIC=1` AND `DATA_CLASSIFICATION=synthetic`.
Customer classification never honours it.

This module reads only the mapping it is handed (by default the current settings' environment) and imports only `config`, so
`deployment` can depend on it and re-export the readers other modules use.
"""
from __future__ import annotations

from typing import Mapping

from config import resolve_environ

LOCAL = "local"
AUTH_MODES = ("none", "entra")
ANONYMOUS_SYNTHETIC_FLAG = "ALLOW_ANONYMOUS_SYNTHETIC"
_TRUE = ("1", "true", "yes", "on")


def _get(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def auth_mode(env: Mapping[str, str] | None = None) -> str:
    """`entra` unless `none` is chosen on purpose. An unknown value is reported by `auth_problems`."""
    env = resolve_environ(env)
    return (_get(env, "AUTH_MODE") or "entra").lower()


def auth_tenant_id(env: Mapping[str, str] | None = None) -> str:
    """The tenant tokens must come from: `AUTH_TENANT_ID`, else the platform's `AZURE_TENANT_ID`."""
    env = resolve_environ(env)
    return _get(env, "AUTH_TENANT_ID") or _get(env, "AZURE_TENANT_ID")


def api_audience(env: Mapping[str, str] | None = None) -> str:
    """The API app registration the token validator checks the audience against."""
    return _get(resolve_environ(env), "API_AUDIENCE")


def explicit_local_dev(env: Mapping[str, str] | None = None) -> bool:
    """`ENVIRONMENT=local` was SET, not merely absent."""
    env = resolve_environ(env)
    return _get(env, "ENVIRONMENT").lower() == LOCAL


def anonymous_synthetic_allowed(env: Mapping[str, str], classification: str | None) -> bool:
    """Anonymous access needs the explicit flag AND synthetic data, so a customer's data is never served unauthenticated."""
    return _get(env, ANONYMOUS_SYNTHETIC_FLAG).lower() in _TRUE and classification == "synthetic"


def _none_problem(env: Mapping[str, str], deployed: bool, classification: str | None) -> str | None:
    if deployed and classification == "customer":
        return ("AUTH_MODE=none is refused with DATA_CLASSIFICATION=customer outside a local "
                "environment (D26): customer payroll is never served without authentication")
    if explicit_local_dev(env) or anonymous_synthetic_allowed(env, classification):
        return None
    return ("AUTH_MODE=none is only for local development: set ENVIRONMENT=local explicitly, "
            "or use AUTH_MODE=entra (the default). A deployed synthetic demo must also set "
            f"{ANONYMOUS_SYNTHETIC_FLAG}=1 with DATA_CLASSIFICATION=synthetic")


def auth_problems(env: Mapping[str, str], *, deployed: bool, classification: str | None) -> list[str]:
    """Everything wrong with the authentication settings, for the startup check to report at once."""
    mode = auth_mode(env)
    if mode not in AUTH_MODES:
        return [f"AUTH_MODE={mode!r} is not one of {', '.join(AUTH_MODES)}"]
    if mode == "none":
        problem = _none_problem(env, deployed, classification)
        return [problem] if problem else []
    problems = []
    if not auth_tenant_id(env):
        hint = "" if _get(env, "AUTH_MODE") else " (AUTH_MODE defaults to entra; for local development set AUTH_MODE=none and ENVIRONMENT=local)"
        problems.append(f"AUTH_MODE=entra needs AUTH_TENANT_ID (or AZURE_TENANT_ID){hint}")
    if not _get(env, "API_AUDIENCE"):
        problems.append("AUTH_MODE=entra needs API_AUDIENCE (the API app registration)")
    return problems
