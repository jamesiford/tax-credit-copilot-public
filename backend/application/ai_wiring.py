"""Composition of model access. [AI-02]

The one place that knows which adapter backs which port. `application/wiring.py`
re-exports these getters, so callers keep one import for everything while the AI
half of the composition stays a readable size.

Everything is built lazily and cached; `set_*` swap a piece for tests and
`reset_ai()` drops it all. Adding a provider is one `register(...)` line in
`_register_builtin_providers`.
"""
from __future__ import annotations

import os
from typing import Any

from application.ai.catalog import CompositeCatalog
from application.ai.narration import NarrationService
from application.ai.providers import ProviderRegistry
from application.ai.router import ModelRouter
from application.ai.settings import AiSettings, load_ai_settings
from application.ai.specs import SpecRegistry

_settings: AiSettings | None = None
_specs: SpecRegistry | None = None
_registry: ProviderRegistry | None = None
_router: ModelRouter | None = None
_service: NarrationService | None = None
_catalog: CompositeCatalog = CompositeCatalog()


def get_ai_settings() -> AiSettings:
    global _settings
    if _settings is None:
        _settings = load_ai_settings(os.environ)
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


def _decorate(runtime: Any, _provider: str) -> Any:
    """Layer the guards over a provider. Outermost first; AI-04 adds resilience here."""
    from application.ai.egress import build_egress_policy
    from application.ai.guarded import GuardedRuntime

    return GuardedRuntime(runtime, build_egress_policy(get_ai_settings().egress_policy))


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
        _service = NarrationService(get_spec_registry(), get_model_router())
    return _service


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
    global _settings, _specs, _registry, _router, _service, _catalog
    _settings = _specs = _registry = _router = _service = None
    _catalog = CompositeCatalog()
