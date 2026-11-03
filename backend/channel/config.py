"""Gateway settings, read once and checked before the app serves. [CH-06]

Every value comes from the environment (App Service settings, `azd env`); none is a
secret. The gateway has no unauthenticated mode at all: there is no `AUTH_MODE`
here to turn off, and one set to anything but `entra` is refused as a
misconfiguration rather than ignored, because a deployment script that sets
`AUTH_MODE=none` expects it to mean something.

A misconfiguration raises `GatewayConfigurationError` at startup. Falling back
would look like it worked, and this process holds the only record of who did what.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from application.deployment import DURABLE_STORES, is_deployed, store_choice

GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

DEFAULT_RATE_LIMIT_PER_MINUTE = 60
#: Slightly above the API's own call timeout (25 s), so the API's structured
#: `timeout` reaches the caller instead of the gateway's connection error.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
#: A claim package is a few hundred rows; the cap is generous and still a cap.
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


class GatewayConfigurationError(RuntimeError):
    """The gateway is configured in a way it must refuse to serve under."""


@dataclass(frozen=True)
class GatewaySettings:
    """What the gateway needs to know, all non-secret."""

    tenant_id: str
    gateway_audience: str
    api_base_url: str
    api_audience: str
    allowed_caller_app_ids: tuple[str, ...] = ()
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    debug_whoami: bool = False
    resolve_display_names: bool = False
    deployed: bool = False
    channel_store: str = "sqlite"

    @property
    def api_scope(self) -> str:
        """The scope a managed identity asks for to call the API: `<audience>/.default`."""
        return f"{self.api_audience.rstrip('/')}/.default"


def _text(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _flag(env: Mapping[str, str], name: str) -> bool:
    return _text(env, name).lower() in ("1", "true", "yes", "on")


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = _text(env, name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise GatewayConfigurationError(f"{name} must be a number; got {raw!r}") from exc
    if not low <= value <= high:
        raise GatewayConfigurationError(f"{name} must be between {low:g} and {high:g}")
    return value


def _problems(env: Mapping[str, str], deployed: bool, store: str) -> list[str]:
    problems = [f"{name} is required" for name in ("TENANT_ID", "GATEWAY_AUDIENCE", "API_BASE_URL", "API_AUDIENCE")
                if not _text(env, name)]
    if _text(env, "TENANT_ID") and not GUID.match(_text(env, "TENANT_ID")):
        problems.append("TENANT_ID must be a GUID")
    mode = _text(env, "AUTH_MODE").lower()
    if mode and mode != "entra":
        problems.append(
            f"AUTH_MODE={mode!r}: the gateway has no unauthenticated mode; unset it or set 'entra'"
        )
    if deployed and store not in DURABLE_STORES:
        problems.append(f"CHANNEL_STORE={store!r} is not durable; a deployed gateway must use 'warehouse'")
    return problems


def load_settings(env: Mapping[str, str] | None = None) -> GatewaySettings:
    """The settings, or `GatewayConfigurationError` naming every problem at once."""
    env = os.environ if env is None else env
    deployed, store = is_deployed(env), store_choice("CHANNEL_STORE", env)
    problems = _problems(env, deployed, store)
    if problems:
        raise GatewayConfigurationError("refusing to start:\n  - " + "\n  - ".join(problems))
    apps = tuple(a.strip().lower() for a in _text(env, "CHANNEL_ALLOWED_CALLER_APP_IDS").split(",") if a.strip())
    return GatewaySettings(
        tenant_id=_text(env, "TENANT_ID").lower(),
        gateway_audience=_text(env, "GATEWAY_AUDIENCE"),
        api_base_url=_text(env, "API_BASE_URL").rstrip("/"),
        api_audience=_text(env, "API_AUDIENCE"),
        allowed_caller_app_ids=apps,
        rate_limit_per_minute=int(_number(env, "CHANNEL_RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE, 1, 6000)),
        request_timeout_seconds=_number(env, "CHANNEL_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS, 1, 600),
        debug_whoami=_flag(env, "CHANNEL_DEBUG_WHOAMI"),
        resolve_display_names=_flag(env, "CHANNEL_RESOLVE_DISPLAY_NAMES"),
        deployed=deployed,
        channel_store=store,
    )
