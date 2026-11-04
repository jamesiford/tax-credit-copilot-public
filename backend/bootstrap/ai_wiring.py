"""Composition of model access. [AI-02]

The one place that knows which adapter backs which port. `bootstrap/wiring.py`
re-exports these getters, so callers keep one import for everything while the AI
half of the composition stays a readable size.

Everything is built lazily and cached; `set_*` swap a piece for tests and
`reset_ai()` drops it all. Adding a provider is one `register(...)` line in
`_register_builtin_providers`.
"""
from __future__ import annotations

import logging
from typing import Any

from application.ai.catalog import CompositeCatalog
from application.ai.narration import NarrationService
from application.ai.providers import ProviderRegistry
from application.ai.router import ModelRouter
from application.ai.settings import AiSettings, load_ai_settings
from application.ai.specs import SpecRegistry
from config import get_settings

log = logging.getLogger(__name__)

_settings: AiSettings | None = None
_specs: SpecRegistry | None = None
_registry: ProviderRegistry | None = None
_router: ModelRouter | None = None
_service: NarrationService | None = None
_catalog: CompositeCatalog = CompositeCatalog()
_telemetry: Any = None
_budget: Any = None
_clock: Any = None


def get_ai_settings() -> AiSettings:
    global _settings
    if _settings is None:
        _settings = load_ai_settings(get_settings().environ)
    return _settings


def set_ai_settings(settings: AiSettings | None) -> None:
    global _settings
    _settings = settings


def get_spec_registry() -> SpecRegistry:
    global _specs
    if _specs is None:
        from agents.factory import all_specs

        _specs = SpecRegistry(all_specs())
    return _specs


def set_spec_registry(specs: SpecRegistry | None) -> None:
    global _specs
    _specs = specs


def _register_builtin_providers(registry: ProviderRegistry) -> None:
    def foundry(settings: AiSettings) -> Any:
        from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog, FoundryAgentRuntime

        catalog = FoundryAgentCatalog(settings, get_spec_registry())
        _catalog.add(catalog)
        return FoundryAgentRuntime(catalog)

    def foundry_connection(settings: AiSettings) -> Any:
        from infrastructure.ai.foundry_model_connection import build_connection_runtime

        runtime = build_connection_runtime(settings, get_spec_registry())
        _catalog.add(runtime.catalog)
        return runtime

    def gateway(settings: AiSettings) -> Any:
        from application.ai.settings import AiConfigurationError
        from infrastructure.ai.auth import build_authenticator
        from infrastructure.ai.chat_model_runtime import ChatModelAgentRuntime
        from infrastructure.ai.openai_compatible import OpenAICompatibleChatModel

        if settings.gateway is None:
            raise AiConfigurationError("the gateway provider is configured without AI_GATEWAY_* settings")
        model = OpenAICompatibleChatModel(settings.gateway, build_authenticator(settings.gateway))
        return ChatModelAgentRuntime(model, settings)

    registry.register("foundry", foundry)
    registry.register("foundry_connection", foundry_connection)
    registry.register("gateway", gateway)


def get_ai_telemetry() -> Any:
    """OpenTelemetry spans and metrics. A no-op until an SDK is configured (main.py does)."""
    global _telemetry
    if _telemetry is None:
        from infrastructure.ai.otel_telemetry import OtelTelemetry

        _telemetry = OtelTelemetry()
    return _telemetry


def set_ai_telemetry(telemetry: Any) -> None:
    global _telemetry
    _telemetry = telemetry


def get_token_budget() -> Any:
    """One budget for every provider, so a refusal on one is a refusal on all."""
    global _budget
    if _budget is None:
        from application.ai.budget import InMemoryTokenBudget

        settings = get_ai_settings()
        _budget = InMemoryTokenBudget(settings.budget_global_daily, settings.budget_principal_daily)
    return _budget


def set_ai_clock(clock: Any) -> None:
    """Swap the clock the resilience layer uses. For tests: virtual time, no real sleeps."""
    global _clock
    _clock = clock


def _decorate(runtime: Any, _provider: str) -> Any:
    """Layer the guards over a provider, outermost first.

    observe → egress → budget → bulkhead → breaker → retry → timeout → the call.
    Every provider gets the same stack from here, so a new one is resilient and
    observed without writing any.
    """
    from application.ai.egress import build_egress_policy
    from application.ai.guarded import GuardedRuntime
    from application.ai.observed import ObservedRuntime
    from infrastructure.ai.resilience import build_resilient_runtime

    settings, telemetry = get_ai_settings(), get_ai_telemetry()
    resilient = build_resilient_runtime(runtime, settings.resilience, clock=_clock, telemetry=telemetry)
    guarded = GuardedRuntime(
        resilient, build_egress_policy(settings.egress_policy), get_token_budget(), telemetry,
    )
    return ObservedRuntime(guarded, telemetry)


def get_provider_registry() -> ProviderRegistry:
    """The registry of provider factories. Public so a deployment or a test can add one."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _register_builtin_providers(_registry)
    return _registry


def set_provider_registry(registry: ProviderRegistry | None) -> None:
    global _registry
    _registry = registry


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter(get_ai_settings(), get_provider_registry(), decorate=_decorate)
    return _router


def set_model_router(router: ModelRouter | None) -> None:
    global _router
    _router = router


def get_narration_service() -> NarrationService:
    global _service
    if _service is None:
        from application.ai.safety.injection import PromptInjectionGuard

        safety = get_ai_settings().safety
        for control in safety.disabled_controls:
            log.warning("AI safety control %s is OFF", control)
        _service = NarrationService(
            get_spec_registry(), get_model_router(),
            PromptInjectionGuard() if safety.injection_guard else None, get_ai_telemetry(),
        )
    return _service


def get_output_policy() -> Any:
    """The output rules for model prose, or None when switched off (and logged as such)."""
    from application.ai.safety.policy import RuleOutputPolicy

    safety = get_ai_settings().safety
    return RuleOutputPolicy(safety.output_allowed_hosts) if safety.output_policy else None


def set_narration_service(service: NarrationService | None) -> None:
    global _service
    _service = service


def get_agent_catalog() -> CompositeCatalog:
    """Every catalog-backed provider's catalog, once the router has built them."""
    get_model_router().statuses()
    return _catalog


def ai_health() -> dict[str, Any]:
    """Provider states for `/api/health` and `/api/ready`. States and short reasons only.

    `state` is `ready` when every provider is, `disabled` when none is configured,
    `degraded` for anything between — a model being down never fails readiness,
    because the engine answers without one.
    """
    statuses = [s.to_dict() for s in get_model_router().statuses()]
    states = {s["state"] for s in statuses}
    overall = "ready" if states == {"ready"} else ("disabled" if states <= {"disabled"} else "degraded")
    return {"state": overall, "providers": statuses, "agents_published": len(get_agent_catalog().entries())}


def reset_ai() -> None:
    """Forget everything built, so the next use reads settings afresh. For tests."""
    global _settings, _specs, _registry, _router, _service, _catalog, _telemetry, _budget
    _settings = _specs = _registry = _router = _service = _telemetry = _budget = None
    _catalog = CompositeCatalog()
