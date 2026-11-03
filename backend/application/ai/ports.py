"""The ports model access depends on. [AI-02]

Small on purpose (Interface Segregation): every Protocol here has at most six
methods, and a consumer takes only the one it uses. A fat `AiProvider` would make
every adapter implement budgets and prompts it has no business with.

The unit a provider offers is an `AgentRuntime` — "stream this agent's answer to
this prompt". A Foundry prompt agent is one; a plain OpenAI-compatible endpoint
wrapped in `ChatModelAgentRuntime` is another. Callers never learn which.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol

from domain.ai import (
    AgentSpec, ChatMessage, EgressDecision, ModelEvent, ModelRole, ModelUsage, OutputVerdict,
    Prompt, ProviderStatus,
)


class ChatModel(Protocol):
    """A chat-completions style model: messages in, a stream of events out."""

    name: str

    def stream(
        self, messages: Sequence[ChatMessage], *, model: str, temperature: float | None = None,
    ) -> AsyncIterator[ModelEvent]: ...

    def status(self) -> ProviderStatus: ...


class AgentRuntime(Protocol):
    """One provider's way of running an agent. Named, so a hop can be reported."""

    name: str

    def ready_for(self, agent_name: str) -> bool: ...

    def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]: ...

    def version_of(self, agent_name: str) -> str | None: ...

    def status(self) -> ProviderStatus: ...


class CatalogEntry(Protocol):
    """One published agent, as shown in the boot log and the health report."""

    name: str
    version: str
    agent_id: str
    portal_url: str


class AgentCatalog(Protocol):
    """Where agents are published and versioned (Foundry's agent service)."""

    def warm(self) -> None: ...

    def has(self, agent_name: str) -> bool: ...

    def version_of(self, agent_name: str) -> str | None: ...

    def entries(self) -> Sequence[CatalogEntry]: ...

    def status(self) -> ProviderStatus: ...


class PromptStore(Protocol):
    """Versioned prompt texts."""

    def get(self, name: str) -> Prompt: ...

    def names(self) -> Sequence[str]: ...


class CallSpan(Protocol):
    """One model call being observed. Attributes are hashes and counts, never text."""

    def finish(
        self, *, outcome: str, usage: ModelUsage | None = None, finish_reason: str | None = None,
        error_type: str | None = None, **attributes: Any,
    ) -> None: ...


class AiTelemetry(Protocol):
    """Spans and metrics for model calls."""

    def start_call(self, *, role: ModelRole, provider: str, model: str | None, agent: str) -> CallSpan: ...

    def count(self, metric: str, value: float = 1, **attributes: Any) -> None: ...


class TokenBudget(Protocol):
    """A daily token ceiling per principal and overall. Refuses rather than overspends."""

    def check(self, principal: str, estimated_tokens: int) -> None: ...

    def record(self, principal: str, usage: ModelUsage) -> None: ...


class EgressPolicy(Protocol):
    """What may leave for a provider. Identifiers never do, whatever the policy."""

    name: str

    def prepare(self, prompt: str, *, role: ModelRole, provider: str) -> EgressDecision: ...


class OutputPolicy(Protocol):
    """Rules a finished narration must satisfy before a reader sees it."""

    def review(self, text: str) -> OutputVerdict: ...


class ConversationStore(Protocol):
    """Redacted recent turns, so "they" and "their" have a referent."""

    def append(self, conversation_id: str, user: str, role: str, text: str, **context: Any) -> None: ...

    def recent(self, conversation_id: str, user: str, limit: int = 6) -> Sequence[Mapping[str, Any]]: ...

    def purge_expired(self) -> int: ...
