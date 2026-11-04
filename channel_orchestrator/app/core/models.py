"""Model access for the orchestrator: the shared adapters, an ordered chain, the egress rule. [CH-08]

The orchestrator reads the same `AI_*` settings as the API and builds the same adapter
(`OpenAICompatibleChatModel`) for each provider in a gateway or mixed chain. A foundry-only chain is not built here:
`model_access.select_model_access` hands it to the framework's own chat client (RM-09), so `build_providers` serves only
the chain that names a gateway. A hosted agent's own model deployment is reached over the Azure OpenAI
v1 chat-completions surface of its Foundry account with the agent's managed identity, so
`foundry` and `gateway` are the same adapter with different settings.

Why this is not `NarrationService`: that path deliberately drops a model's tool calls
(agents hold no tools, ADR-004) and the orchestrator needs them, because the MODEL chooses
which deterministic tool runs. What it keeps from the platform's AI layer: the settings,
the provider chain's rule (fall to the next provider only when one fails; never splice two
models' sentences, so a turn's text is one provider's whole answer), the egress policy (an
identifier never leaves, whatever the policy) and the injection screen.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.settings import OrchestratorConfigError, OrchestratorSettings
from application.ai.egress import build_egress_policy
from application.ai.gateway_settings import GatewaySettings
from application.ai.safety.injection import PromptInjectionGuard
from domain.ai import (
    ChatMessage, EgressRefused, ModelError, ModelRole, NarrationUnavailable, StreamEnd, TextDelta, ToolCall, ToolSpec,
    supports_temperature,
)
from infrastructure.ai.auth import build_authenticator
from infrastructure.ai.openai_compatible import OpenAICompatibleChatModel

log = logging.getLogger("tcc.orchestrator.models")

FOUNDRY_AUDIENCE = "https://cognitiveservices.azure.com"


@dataclass(frozen=True)
class ModelTurn:
    """One completed model turn: text and/or the tools it asked for, and who answered."""

    text: str
    tool_calls: tuple[ToolCall, ...]
    provider: str
    model: str
    hops: tuple[str, ...]


@dataclass(frozen=True)
class Provider:
    name: str
    chat: OpenAICompatibleChatModel
    model: str
    supports_tools: bool


def foundry_openai_base(project_endpoint: str) -> str:
    """The account's Azure OpenAI v1 base: `https://<account>.openai.azure.com/openai`.

    Not the project endpoint's own host. From the hosted runtime `<account>.services.ai.azure.com` and
    `<account>.cognitiveservices.azure.com` do not resolve ("Temporary failure in name resolution",
    shown by `/netcheck` and by the documented sample's own call, `/modelprobe`) while
    `<account>.openai.azure.com` resolves and answers, with the same account, token and deployment. [CH-14]
    A host that is not a public-cloud `services.ai.azure.com` name keeps its own host.
    """
    parsed = urlparse(project_endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise OrchestratorConfigError("FOUNDRY_PROJECT_ENDPOINT must be an https:// URL")
    account, _, suffix = parsed.netloc.partition(".")
    host = f"{account}.openai.azure.com" if suffix == "services.ai.azure.com" else parsed.netloc
    return f"https://{host}/openai"


def build_providers(settings: OrchestratorSettings) -> list[Provider]:
    """The providers for the planner/narrator role, in the configured order."""
    ai, role, built = settings.ai, ModelRole.NARRATOR, []
    for name in ai.chain_for(role):
        if name == "gateway":
            gateway = ai.gateway
            if gateway is None:
                raise OrchestratorConfigError("gateway is in the provider chain without AI_GATEWAY_* settings")
            built.append(Provider(name, OpenAICompatibleChatModel(gateway, build_authenticator(gateway)),
                                  ai.model_for(role, name), gateway.supports_tools))
        elif name == "foundry":
            if not ai.foundry_endpoint:
                raise OrchestratorConfigError("foundry is in the provider chain but FOUNDRY_PROJECT_ENDPOINT is not set")
            gateway = GatewaySettings(
                endpoint=foundry_openai_base(ai.foundry_endpoint), auth="entra_token", entra_audience=FOUNDRY_AUDIENCE,
                timeout_s=ai.resilience.call_timeout_s, connect_timeout_s=5.0,
            )
            chat = OpenAICompatibleChatModel(gateway, build_authenticator(gateway))
            chat.name = "foundry"
            built.append(Provider(name, chat, ai.model_for(role, name), True))
    return built


class ModelChain:
    """Tries each provider in order; a failure before a whole answer moves to the next."""

    def __init__(self, providers: Sequence[Provider], *, egress_policy: str, timeout_seconds: float,
                 injection: PromptInjectionGuard | None = None) -> None:
        self._providers, self._timeout = tuple(providers), timeout_seconds
        self._egress, self._injection = build_egress_policy(egress_policy), injection

    @property
    def configured(self) -> bool:
        return bool(self._providers)

    @property
    def tools_available(self) -> bool:
        """True when the first provider that could answer offers tool calling."""
        return any(p.supports_tools for p in self._providers)

    def screen(self, text: str) -> bool:
        """True when `text` carries an instruction-override attempt: no model is called for it."""
        return bool(self._injection and self._injection.scan(text).flagged)

    async def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = (), *, prefer: str | None = None) -> ModelTurn:
        """One whole answer from the first provider that gives one, or `NarrationUnavailable`.

        `prefer` names the provider that answered earlier in the same turn: a tool loop stays with
        one model while it can, and moves on only when that provider fails.
        """
        prompt = "\n".join(m.content for m in messages)
        ordered = sorted(self._providers, key=lambda p: p.name != prefer)
        hops: list[str] = []
        for provider in ordered:
            if tools and not provider.supports_tools:
                continue
            hops.append(provider.name)
            decision = self._egress.prepare(prompt, role=ModelRole.NARRATOR, provider=provider.name)
            if not decision.allowed:
                log.warning("egress refused for %s: %s", provider.name, decision.policy)
                continue
            try:
                return await asyncio.wait_for(self._one(provider, messages, tools, tuple(hops)), self._timeout)
            except (ModelError, asyncio.TimeoutError, EgressRefused) as exc:
                log.warning("provider %s failed (%s: %s); trying the next", provider.name, type(exc).__name__, str(exc)[:200])
        raise NarrationUnavailable("no provider could answer", tuple(hops))

    async def _one(self, provider: Provider, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec],
                   hops: tuple[str, ...]) -> ModelTurn:
        text, calls, model = "", [], provider.model
        temperature = 0.2 if supports_temperature(provider.model) else None
        async for event in provider.chat.stream(messages, model=provider.model, temperature=temperature, tools=tools):
            if isinstance(event, TextDelta):
                text += event.text
            elif isinstance(event, ToolCall):
                calls.append(event)
            elif isinstance(event, StreamEnd):
                model = event.model or model
        return ModelTurn(text, tuple(calls), provider.name, model, hops)
