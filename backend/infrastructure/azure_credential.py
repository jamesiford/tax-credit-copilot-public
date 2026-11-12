"""The one place an Azure credential is built, and the one cache of it. [03.4]

`DefaultAzureCredential` used to be constructed in fourteen places. Each fresh
instance re-probes the managed-identity endpoint, and on a developer machine
that probe is a guaranteed multi-second wait before the chain falls through to
`az login`, repeated at every read. One shared instance pays it at most once,
and locally it does not pay it at all.

The policy is deliberately small:

- **Deployed** (`ENVIRONMENT` is anything but `local`): the SDK default chain,
  unchanged. The user-assigned identity is selected by `AZURE_CLIENT_ID`, which
  the SDK reads itself; it is passed explicitly only when set.
- **Local**: the managed-identity credential is left out of the chain, so there
  is no IMDS wait. Environment variables, `az login`, `azd`, VS Code and
  PowerShell still work.
- **`AZURE_TOKEN_CREDENTIALS`** set: the operator has chosen, so no exclusions
  are passed and the SDK applies the value itself (`dev`, `prod`, or one
  credential name; azure-identity 1.27.0 accepts exactly those and raises
  `ValueError` on anything else).

This module imports only the standard library and, lazily, `azure.identity`, so
`data/`, `telemetry.py` and the adapters can all use it without a cycle.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from config import get_settings

#: Refresh a cached token this long before it expires.
_REFRESH_MARGIN_SECONDS = 300

_lock = threading.Lock()
_shared: Any = None
_tokens: dict[str, tuple[str, float]] = {}


def build_credential(
    *, deployed: bool, managed_identity_client_id: str | None = None, token_credentials: str = ""
) -> Any:
    """A new credential under the policy above. Pure: no globals, no environment."""
    from azure.identity import DefaultAzureCredential

    options: dict[str, Any] = {}
    if managed_identity_client_id:
        options["managed_identity_client_id"] = managed_identity_client_id
    if not deployed and not token_credentials.strip():
        options["exclude_managed_identity_credential"] = True
    return DefaultAzureCredential(**options)


def _settings_credential() -> Any:
    identity = get_settings().identity
    return build_credential(
        deployed=identity.deployed,
        managed_identity_client_id=identity.azure_client_id,
        token_credentials=identity.token_credentials,
    )


def shared_credential() -> Any:
    """The process-wide credential, built on first use and then reused."""
    global _shared
    if _shared is None:
        with _lock:
            if _shared is None:
                _shared = _settings_credential()
    return _shared


def new_credential() -> Any:
    """A fresh instance, for the rare caller that must bypass the shared one's token cache."""
    return _settings_credential()


def cached_token(scope: str) -> str:
    """A bearer token for `scope`, reused until shortly before it expires."""
    now = time.time()
    with _lock:
        cached = _tokens.get(scope)
        if cached and cached[1] - now > _REFRESH_MARGIN_SECONDS:
            return cached[0]
    token = shared_credential().get_token(scope)
    with _lock:
        _tokens[scope] = (token.token, float(token.expires_on))
    return token.token


def reset_for_tests() -> None:
    """Forget the shared credential and every cached token."""
    global _shared
    with _lock:
        _shared = None
        _tokens.clear()
