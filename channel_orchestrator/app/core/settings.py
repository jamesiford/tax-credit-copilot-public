"""Orchestrator configuration, read once at start. [CH-08]

Every value is an environment variable and none is a secret. Model access is the SAME
`AI_*` configuration the API reads (`application.ai.settings.load_ai_settings`), so a
customer who points the platform at a gateway points the orchestrator at it with the
same settings. The Foundry platform sets `FOUNDRY_*` and `APPLICATIONINSIGHTS_*`
itself; those names are reserved and are never set from Terraform or the publish script.

A misconfiguration raises `OrchestratorConfigError` at start. A container that boots
with half a configuration answers every question with an apology, which looks like a
model problem.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from application.ai.settings import AiSettings, load_ai_settings

_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
CHANNELS = ("teams", "m365-copilot")
IDENTITY_SOURCES = ("original-subject", "platform", "client-headers", "agent-user-id")


class OrchestratorConfigError(ValueError):
    """The orchestrator cannot run as configured."""


@dataclass(frozen=True)
class OrchestratorSettings:
    """What one orchestrator process needs; `ai` is the shared model-access configuration."""

    gateway_url: str
    gateway_audience: str
    tenant_id: str
    ai: AiSettings
    channel: str = "teams"
    max_tool_calls: int = 8
    confirm_ttl_seconds: int = 300
    state_ttl_seconds: int = 3600
    request_timeout_seconds: float = 40.0
    turn_timeout_seconds: float = 90.0
    debug_whoami: bool = False
    identity_sources: tuple[str, ...] = ("original-subject", "platform", "agent-user-id")
    agent_name: str = "tcc-channel-orchestrator"
    agent_version: str = "0"

    @property
    def gateway_scope(self) -> str:
        """What a managed identity asks for to call the gateway: `<audience>/.default`."""
        return f"{self.gateway_audience.rstrip('/')}/.default"


def _text(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name) or default).strip()


def _integer(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = _text(env, name)
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise OrchestratorConfigError(f"{name} must be a whole number; got {raw!r}") from exc
    if not low <= value <= high:
        raise OrchestratorConfigError(f"{name} must be between {low} and {high}")
    return value


def _flag(env: Mapping[str, str], name: str) -> bool:
    return _text(env, name).lower() in ("1", "true", "yes", "on")


def _identity_sources(env: Mapping[str, str]) -> tuple[str, ...]:
    chosen = tuple(p.strip().lower() for p in _text(env, "CHANNEL_IDENTITY_SOURCES", "original-subject,platform,agent-user-id").split(",") if p.strip())
    unknown = [p for p in chosen if p not in IDENTITY_SOURCES]
    if unknown or not chosen:
        raise OrchestratorConfigError(f"CHANNEL_IDENTITY_SOURCES must list some of {IDENTITY_SOURCES}; got {unknown or 'nothing'}")
    return chosen


def _problems(env: Mapping[str, str]) -> list[str]:
    found = [f"{name} is required" for name in ("CHANNEL_GATEWAY_URL", "CHANNEL_GATEWAY_AUDIENCE", "TENANT_ID") if not _text(env, name)]
    if _text(env, "TENANT_ID") and not _GUID.match(_text(env, "TENANT_ID")):
        found.append("TENANT_ID must be a GUID")
    if _text(env, "CHANNEL_GATEWAY_URL") and not _text(env, "CHANNEL_GATEWAY_URL").lower().startswith("https://"):
        found.append("CHANNEL_GATEWAY_URL must be an https:// URL")
    if _text(env, "CHANNEL_NAME", "teams") not in CHANNELS:
        found.append(f"CHANNEL_NAME must be one of {CHANNELS}")
    return found


def load_settings(env: Mapping[str, str]) -> OrchestratorSettings:
    """Read and check the environment, or raise `OrchestratorConfigError` naming every problem."""
    problems = _problems(env)
    if problems:
        raise OrchestratorConfigError("; ".join(problems))
    try:
        ai = load_ai_settings(env)
    except ValueError as exc:
        raise OrchestratorConfigError(str(exc)) from exc
    if "foundry_connection" in ai.providers_in_use:
        raise OrchestratorConfigError(
            "foundry_connection serves prompt agents only; a hosted agent calls its model as `foundry` or `gateway`"
        )
    return OrchestratorSettings(
        gateway_url=_text(env, "CHANNEL_GATEWAY_URL").rstrip("/"),
        gateway_audience=_text(env, "CHANNEL_GATEWAY_AUDIENCE"), tenant_id=_text(env, "TENANT_ID").lower(), ai=ai,
        channel=_text(env, "CHANNEL_NAME", "teams"),
        max_tool_calls=_integer(env, "CHANNEL_MAX_TOOL_CALLS", 8, 1, 20),
        confirm_ttl_seconds=_integer(env, "CHANNEL_CONFIRM_TTL_SECONDS", 300, 30, 3600),
        state_ttl_seconds=_integer(env, "CHANNEL_STATE_TTL_SECONDS", 3600, 60, 86400),
        request_timeout_seconds=float(_integer(env, "CHANNEL_REQUEST_TIMEOUT_SECONDS", 40, 5, 300)),
        turn_timeout_seconds=float(_integer(env, "CHANNEL_TURN_TIMEOUT_SECONDS", 90, 10, 600)),
        debug_whoami=_flag(env, "CHANNEL_DEBUG_WHOAMI"),
        identity_sources=_identity_sources(env),
        agent_name=_text(env, "FOUNDRY_AGENT_NAME", "tcc-channel-orchestrator"),
        agent_version=_text(env, "FOUNDRY_AGENT_VERSION", "0"),
    )
