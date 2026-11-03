"""The external model gateway's settings. [AI-03]

The customer's gateway is its own service and what we know of it is short: an
HTTPS endpoint, OpenAI-style chat completions, streaming and tool calling. What
we do NOT know — its authentication, dialect, model names — is therefore pure
configuration, and there is deliberately NO default for `AI_GATEWAY_AUTH`: a
gateway in the provider chain without an explicit scheme fails at startup, because
guessing "none" would send prompts unauthenticated and guessing a key would fail
only at the first question.

Secrets (`AI_GATEWAY_API_KEY`, `AI_GATEWAY_OAUTH_CLIENT_SECRET`) arrive as
App Service Key Vault *references* resolved by the platform into the environment;
nothing in the repository, tfvars or Terraform state holds them. The preferred
scheme needs no secret at all: `entra_token` uses the app's managed identity.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

AUTH_SCHEMES = ("none", "api_key", "oauth_client_credentials", "entra_token")
API_STYLES = ("openai_v1", "azure_deployments")


class GatewayConfigurationError(ValueError):
    """The gateway is in the provider chain and cannot be used as configured."""


@dataclass(frozen=True)
class GatewaySettings:
    endpoint: str
    auth: str
    api_style: str = "openai_v1"
    api_key: str = field(default="", repr=False)
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    oauth_token_url: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = field(default="", repr=False)
    oauth_scope: str = ""
    entra_audience: str = ""
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    timeout_s: float = 30.0
    connect_timeout_s: float = 5.0
    tls_verify: bool = True
    streaming: bool = True
    supports_tools: bool = True
    api_version: str = "2024-10-21"


def _flag(env: Mapping[str, Any], name: str, default: bool) -> bool:
    raw = str(env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise GatewayConfigurationError(f"{name} must be true or false; got {raw!r}")


def _seconds(env: Mapping[str, Any], name: str, default: float) -> float:
    raw = str(env.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError as exc:
        raise GatewayConfigurationError(f"{name} must be a number of seconds; got {raw!r}") from exc


def _headers(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise GatewayConfigurationError("AI_GATEWAY_EXTRA_HEADERS must be a JSON object of strings") from exc
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise GatewayConfigurationError("AI_GATEWAY_EXTRA_HEADERS must be a JSON object of strings")
    return value


def _require(settings: GatewaySettings) -> GatewaySettings:
    """Each scheme names what it cannot work without."""
    needs = {
        "api_key": ("api_key",),
        "oauth_client_credentials": ("oauth_token_url", "oauth_client_id", "oauth_client_secret"),
        "entra_token": ("entra_audience",),
        "none": (),
    }[settings.auth]
    missing = [name for name in needs if not getattr(settings, name)]
    if missing:
        raise GatewayConfigurationError(
            f"AI_GATEWAY_AUTH={settings.auth} needs {', '.join('AI_GATEWAY_' + m.upper() for m in missing)}"
        )
    if not settings.endpoint.lower().startswith("https://"):
        raise GatewayConfigurationError("AI_GATEWAY_ENDPOINT must be an https:// URL")
    return settings


def load_gateway_settings(env: Mapping[str, Any]) -> GatewaySettings:
    """Read the gateway's variables. Called only when `gateway` is in the chain."""
    get = lambda name, default="": str(env.get(name) or default).strip()  # noqa: E731
    endpoint, auth, style = get("AI_GATEWAY_ENDPOINT").rstrip("/"), get("AI_GATEWAY_AUTH").lower(), get("AI_GATEWAY_API_STYLE", "openai_v1").lower()
    if not endpoint:
        raise GatewayConfigurationError("gateway is in the provider chain but AI_GATEWAY_ENDPOINT is not set")
    if auth not in AUTH_SCHEMES:
        raise GatewayConfigurationError(
            f"AI_GATEWAY_AUTH must be set explicitly to one of {AUTH_SCHEMES}; got {auth!r}"
        )
    if style not in API_STYLES:
        raise GatewayConfigurationError(f"AI_GATEWAY_API_STYLE must be one of {API_STYLES}; got {style!r}")
    return _require(GatewaySettings(
        endpoint=endpoint, auth=auth, api_style=style, api_key=get("AI_GATEWAY_API_KEY"),
        api_key_header=get("AI_GATEWAY_API_KEY_HEADER", "Authorization"),
        api_key_prefix=str(env.get("AI_GATEWAY_API_KEY_PREFIX", "Bearer ")),
        oauth_token_url=get("AI_GATEWAY_OAUTH_TOKEN_URL"), oauth_client_id=get("AI_GATEWAY_OAUTH_CLIENT_ID"),
        oauth_client_secret=get("AI_GATEWAY_OAUTH_CLIENT_SECRET"), oauth_scope=get("AI_GATEWAY_OAUTH_SCOPE"),
        entra_audience=get("AI_GATEWAY_ENTRA_AUDIENCE"), extra_headers=_headers(get("AI_GATEWAY_EXTRA_HEADERS")),
        timeout_s=_seconds(env, "AI_GATEWAY_TIMEOUT_SECONDS", 30.0),
        connect_timeout_s=_seconds(env, "AI_GATEWAY_CONNECT_TIMEOUT_SECONDS", 5.0),
        tls_verify=_flag(env, "AI_GATEWAY_TLS_VERIFY", True), streaming=_flag(env, "AI_GATEWAY_STREAMING", True),
        supports_tools=_flag(env, "AI_GATEWAY_SUPPORTS_TOOLS", True),
        api_version=get("AI_GATEWAY_API_VERSION", "2024-10-21"),
    ))
