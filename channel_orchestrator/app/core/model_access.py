"""Which model path serves a turn, chosen once from `AI_PROVIDER_CHAIN`. [RM-09]

Two paths, one interface (`ModelAccess`), and a rule that says which one a deployment gets:

- **A chain that is exactly `foundry`** is served by the Microsoft Agent Framework's own chat client
  (`maf_foundry_client`), pointed at the Foundry account's OpenAI v1 host with the agent's Entra identity.
  There is nothing to fail over to, so the framework's client needs no help.
- **Any chain that names `gateway`** (alone, or with `foundry` before or after it) is served by `ModelChain`
  through `PortChatClient`. The framework has no failover client (finding F-05) and the customer's gateway
  has its own dialect, authentication and egress policy, which `ModelChain` already owns.

This module holds no SDK: the framework client is built in the `maf_*` layer from the plain description
`FoundryModelAccess` carries, so the layering rule (the agent framework and the Azure SDKs stay in their own
modules) is unchanged.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.core.models import FOUNDRY_AUDIENCE, ModelChain, ModelTurn, build_providers, foundry_openai_base
from app.core.settings import OrchestratorConfigError, OrchestratorSettings
from application.ai.safety.injection import PromptInjectionGuard
from domain.ai import ChatMessage, ModelRole, NarrationUnavailable, ToolSpec

TokenProvider = Callable[[], "str | Awaitable[str]"]


class ModelAccess(Protocol):
    """What the planner needs of whichever path serves the model."""

    @property
    def configured(self) -> bool: ...

    @property
    def tools_available(self) -> bool: ...

    def screen(self, text: str) -> bool: ...

    async def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = (), *, prefer: str | None = None) -> ModelTurn: ...


def foundry_v1_base(project_endpoint: str) -> str:
    """The base MAF's OpenAI client is given: the account's OpenAI host (not the project host) plus `/openai/v1`.

    `foundry_openai_base` explains the host (the hosted runtime resolves `<account>.openai.azure.com` and not the
    project's `services.ai.azure.com`); the client appends `/chat/completions`, so the request URL is the one the
    shared adapter has always used.
    """
    return f"{foundry_openai_base(project_endpoint)}/v1"


@dataclass(frozen=True)
class FoundryModelAccess:
    """A foundry-only chain, described without any SDK. `credential` is a token provider (tests pass a fake);
    left empty, the MAF layer uses `DefaultAzureCredential`, the agent's managed identity when deployed. No key exists."""

    base_url: str
    model: str
    egress_policy: str
    timeout_seconds: float
    scope: str = f"{FOUNDRY_AUDIENCE}/.default"
    injection: PromptInjectionGuard | None = None
    credential: TokenProvider | None = None

    @property
    def configured(self) -> bool:
        return True

    @property
    def tools_available(self) -> bool:
        """A Foundry deployment always offers tool calling, so the json mode is never this path's."""
        return True

    def screen(self, text: str) -> bool:
        """True when `text` carries an instruction-override attempt: no model is called for it."""
        return bool(self.injection and self.injection.scan(text).flagged)

    async def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = (), *, prefer: str | None = None) -> ModelTurn:
        """Unreachable by design: only the json mode calls a model outside the agent's loop, and only a gateway
        without tool calling selects it. Refusing here keeps a future caller from finding a second model path."""
        raise NarrationUnavailable("the foundry provider answers through the agent's chat client only", ("foundry",))


def _injection(settings: OrchestratorSettings) -> PromptInjectionGuard | None:
    return PromptInjectionGuard() if settings.ai.safety.injection_guard else None


def build_chain(settings: OrchestratorSettings) -> ModelChain:
    """The ordered provider chain (`ModelChain`), for a gateway or a mixed configuration."""
    return ModelChain(
        build_providers(settings), egress_policy=settings.ai.egress_policy,
        timeout_seconds=settings.ai.resilience.total_deadline_s, injection=_injection(settings),
    )


def select_model_access(settings: OrchestratorSettings) -> ModelAccess:
    """The framework's client for a foundry-only chain, `ModelChain` for every other one (the rule is in the docstring above)."""
    ai = settings.ai
    if ai.chain_for(ModelRole.NARRATOR) != ("foundry",):
        return build_chain(settings)
    if not ai.foundry_endpoint:
        raise OrchestratorConfigError("foundry is in the provider chain but FOUNDRY_PROJECT_ENDPOINT is not set")
    return FoundryModelAccess(
        foundry_v1_base(ai.foundry_endpoint), ai.model_for(ModelRole.NARRATOR, "foundry"), ai.egress_policy,
        ai.resilience.total_deadline_s, injection=_injection(settings),
    )
