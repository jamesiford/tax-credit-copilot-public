"""The one place AI environment variables are read. [AI-02, AI-03]

Everything model-related is configuration, so a deployment can change provider,
model, order, ceilings and timeouts without a code change — and so a test can
build any of those from a plain dict, with no `os.environ` monkeypatching.

    AI_PROVIDER_CHAIN                  foundry                  ordered providers; first that answers wins
    AI_PROVIDER_CHAIN__NARRATOR        (inherits)               per-role override: ROUTER | NARRATOR | ANALYSIS
    AI_MODEL_<ROLE>[__<PROVIDER>]      (provider default)       model name; the double-underscore form wins
    AI_EGRESS_POLICY                   allow_all                allow_all | aggregates_only | block
    AI_AGENT_VERSION_PINS              (none)                   AgentName=version,AgentName=version
    AI_TOKEN_BUDGET_DAILY              (none)                   global ceiling; unset = no ceiling
    AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY (none)                  per-user ceiling
    AI_INJECTION_GUARD / AI_OUTPUT_POLICY / AI_OUTPUT_ALLOWED_HOSTS   see `safety/settings.py`

The gateway's own variables live in `gateway_settings.py`; the Foundry ones keep
their existing names (`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from application.ai.gateway_settings import GatewaySettings, load_gateway_settings
from application.ai.safety.settings import SafetySettings, load_safety_settings
from domain.ai import ModelRole

DEFAULT_FOUNDRY_MODEL = "gpt-5.4-mini"
EGRESS_POLICIES = ("allow_all", "aggregates_only", "block")
KNOWN_PROVIDERS = ("foundry", "foundry_connection", "gateway")


class AiConfigurationError(ValueError):
    """The AI settings cannot work. Raised at startup, not at the first question."""


@dataclass(frozen=True)
class ResilienceSettings:
    """How hard to try, and when to stop (AI-04). Defaults suit an interactive chat."""

    call_timeout_s: float = 30.0
    retry_attempts: int = 3
    retry_base_s: float = 0.5
    retry_max_s: float = 8.0
    total_deadline_s: float = 45.0
    breaker_failures: int = 5
    breaker_reset_s: float = 30.0
    bulkhead_limit: int = 8


@dataclass(frozen=True)
class AiSettings:
    """The validated, frozen AI configuration. Build it with `load_ai_settings`."""

    provider_chain: tuple[str, ...] = ("foundry",)
    role_chains: Mapping[ModelRole, tuple[str, ...]] = field(default_factory=dict)
    models: Mapping[str, str] = field(default_factory=dict)
    foundry_endpoint: str = ""
    foundry_model: str = DEFAULT_FOUNDRY_MODEL
    connection_name: str = ""
    egress_policy: str = "allow_all"
    version_pins: Mapping[str, str] = field(default_factory=dict)
    budget_global_daily: int | None = None
    budget_principal_daily: int | None = None
    resilience: ResilienceSettings = field(default_factory=ResilienceSettings)
    gateway: GatewaySettings | None = None
    safety: SafetySettings = field(default_factory=SafetySettings)

    def chain_for(self, role: ModelRole) -> tuple[str, ...]:
        """Providers to try for `role`, in order."""
        return tuple(self.role_chains.get(role) or self.provider_chain)

    def model_for(self, role: ModelRole, provider: str) -> str:
        """The model `role` uses on `provider`: provider-specific, then role-wide, then Foundry's default."""
        for key in (f"{role.value}__{provider}", role.value):
            if self.models.get(key):
                return self.models[key]
        if provider == "foundry":
            return self.foundry_model
        raise AiConfigurationError(
            f"no model is set for {role.value} on {provider}; set AI_MODEL_{role.name}__{provider.upper()}"
        )

    @property
    def providers_in_use(self) -> tuple[str, ...]:
        seen: list[str] = []
        for chain in (self.provider_chain, *self.role_chains.values()):
            seen.extend(p for p in chain if p not in seen)
        return tuple(seen)


def _text(env: Mapping[str, Any], name: str, default: str = "") -> str:
    return str(env.get(name) or default).strip()


def _number(env: Mapping[str, Any], name: str, default: float, cast=float):
    raw = _text(env, name)
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError as exc:
        raise AiConfigurationError(f"{name} must be a number; got {raw!r}") from exc


def _optional_int(env: Mapping[str, Any], name: str) -> int | None:
    raw = _text(env, name)
    return _number(env, name, 0, int) if raw else None


def _chain(raw: str) -> tuple[str, ...]:
    return tuple(p.strip().lower() for p in raw.split(",") if p.strip())


def parse_pins(raw: str) -> dict[str, str]:
    """`Agent=3,Other=7` → {"Agent": "3", "Other": "7"}. A malformed pair is an error, not skipped."""
    pins: dict[str, str] = {}
    for pair in (p for p in raw.split(",") if p.strip()):
        name, sep, version = pair.partition("=")
        if not sep or not name.strip() or not version.strip():
            raise AiConfigurationError(f"AI_AGENT_VERSION_PINS entry {pair!r} must look like AgentName=version")
        pins[name.strip()] = version.strip()
    return pins


def _role_chains(env: Mapping[str, Any]) -> dict[ModelRole, tuple[str, ...]]:
    found = {}
    for role in ModelRole:
        raw = _text(env, f"AI_PROVIDER_CHAIN__{role.name}")
        if raw:
            found[role] = _chain(raw)
    return found


def _models(env: Mapping[str, Any]) -> dict[str, str]:
    models = {}
    for role in ModelRole:
        for suffix, key in (("", role.value), *((f"__{p.upper()}", f"{role.value}__{p}") for p in KNOWN_PROVIDERS)):
            value = _text(env, f"AI_MODEL_{role.name}{suffix}")
            if value:
                models[key] = value
    return models


def _resilience(env: Mapping[str, Any]) -> ResilienceSettings:
    base = ResilienceSettings()
    return ResilienceSettings(
        call_timeout_s=_number(env, "AI_CALL_TIMEOUT_SECONDS", base.call_timeout_s),
        retry_attempts=_number(env, "AI_RETRY_MAX_ATTEMPTS", base.retry_attempts, int),
        retry_base_s=_number(env, "AI_RETRY_BASE_SECONDS", base.retry_base_s),
        retry_max_s=_number(env, "AI_RETRY_MAX_SECONDS", base.retry_max_s),
        total_deadline_s=_number(env, "AI_TOTAL_DEADLINE_SECONDS", base.total_deadline_s),
        breaker_failures=_number(env, "AI_BREAKER_FAILURE_THRESHOLD", base.breaker_failures, int),
        breaker_reset_s=_number(env, "AI_BREAKER_RESET_SECONDS", base.breaker_reset_s),
        bulkhead_limit=_number(env, "AI_BULKHEAD_MAX_CONCURRENT", base.bulkhead_limit, int),
    )


def load_ai_settings(env: Mapping[str, Any]) -> AiSettings:
    """Read, validate and freeze the AI settings. An unusable combination raises."""
    chain = _chain(_text(env, "AI_PROVIDER_CHAIN", "foundry")) or ("foundry",)
    egress = _text(env, "AI_EGRESS_POLICY", "allow_all").lower()
    if egress not in EGRESS_POLICIES:
        raise AiConfigurationError(f"AI_EGRESS_POLICY must be one of {EGRESS_POLICIES}; got {egress!r}")
    role_chains = _role_chains(env)
    in_use = {p for c in (chain, *role_chains.values()) for p in c}
    settings = AiSettings(
        provider_chain=chain, role_chains=role_chains, models=_models(env),
        foundry_endpoint=_text(env, "FOUNDRY_PROJECT_ENDPOINT"),
        foundry_model=_text(env, "FOUNDRY_MODEL", DEFAULT_FOUNDRY_MODEL),
        connection_name=_text(env, "AI_FOUNDRY_CONNECTION_NAME"), egress_policy=egress,
        version_pins=parse_pins(_text(env, "AI_AGENT_VERSION_PINS")),
        budget_global_daily=_optional_int(env, "AI_TOKEN_BUDGET_DAILY"),
        budget_principal_daily=_optional_int(env, "AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY"),
        resilience=_resilience(env), safety=load_safety_settings(env),
        gateway=load_gateway_settings(env) if "gateway" in in_use else None,
    )
    if "foundry_connection" in in_use and not settings.connection_name:
        raise AiConfigurationError("foundry_connection is in the provider chain but AI_FOUNDRY_CONNECTION_NAME is not set")
    return settings
