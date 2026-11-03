"""Value objects for model access: what is asked, what comes back, what can go wrong. [AI-02]

Stdlib only, like the rest of `domain/`. Nothing here knows a provider, an SDK or
a URL: a Foundry prompt agent, an OpenAI-compatible gateway and a test fake all
speak these types, which is what lets one contract suite hold every adapter to
the same behaviour (Liskov) and lets a provider be added without touching a
pipeline (open/closed).

The error taxonomy is small on purpose. A caller decides between four things —
try again later, try the next provider, fix the request, or give up — so
adapters map whatever their SDK raises onto these and nothing finer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Union


class ModelRole(str, Enum):
    """What a model is being used FOR, so each job can use a different model."""

    ROUTER = "router"
    NARRATOR = "narrator"
    ANALYSIS = "analysis"


@dataclass(frozen=True)
class ModelRef:
    """A model as one provider names it."""

    provider: str
    model: str


@dataclass(frozen=True)
class AgentSpec:
    """One agent as DATA: who it is, what it is told, which job it does.

    `instructions` come from the versioned prompt files (`agents/prompts`), never
    from code, so changing a prompt is a reviewable diff with a version bump.
    No tools are ever attached: agents narrate, tools calculate [ADR-004].
    """

    name: str
    instructions: str
    role: ModelRole = ModelRole.NARRATOR
    temperature: float | None = 0.2
    profile: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatMessage:
    """One message to a chat-completions style model."""

    role: str
    content: str


@dataclass(frozen=True)
class TextDelta:
    """A piece of generated text."""

    text: str


@dataclass(frozen=True)
class ModelUsage:
    """Tokens spent. `estimated` is True when the provider reported none."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated: bool = False

    @property
    def total(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)


@dataclass(frozen=True)
class StreamEnd:
    """The last event of a narration: who actually answered.

    `hops` lists every provider tried, in order, so a fallback is visible in
    telemetry and in the audit row rather than inferred from a missing span.
    """

    provider: str
    model: str | None = None
    agent_version: str | None = None
    hops: tuple[str, ...] = ()
    finish_reason: str | None = None

    @property
    def fallback_used(self) -> bool:
        return len(self.hops) > 1


ModelEvent = Union[TextDelta, ModelUsage, StreamEnd]

PROVIDER_STATES = ("ready", "warming", "degraded", "unavailable", "disabled")


@dataclass(frozen=True)
class ProviderStatus:
    """A provider's health, safe to show: a state and a short reason, no secrets."""

    name: str
    state: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.state not in PROVIDER_STATES:
            raise ValueError(f"state must be one of {PROVIDER_STATES}, got {self.state!r}")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state, "detail": self.detail}


# ---------------------------------------------------------------------- errors


class ModelError(Exception):
    """Base of the taxonomy. `retryable` says whether the same call may succeed later."""

    retryable = False


class ModelUnavailable(ModelError):
    """The provider could not be reached or answered 5xx."""

    retryable = True


class ModelTimeout(ModelError):
    """The provider did not answer in time."""

    retryable = True


class ModelRateLimited(ModelError):
    """The provider asked us to slow down; `retry_after` is seconds, when it said."""

    retryable = True

    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ModelBadRequest(ModelError):
    """The request itself was refused (4xx other than 429). Retrying cannot help."""


class ModelAuth(ModelError):
    """The provider refused our credentials. Retrying cannot help."""


class NarrationUnavailable(Exception):
    """Every provider failed or was refused. Callers fall back to the engine's own blocks."""

    def __init__(self, message: str = "no provider could answer", hops: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.hops = hops


def supports_temperature(model: str) -> bool:
    """GPT-5 deployments reject legacy sampling parameters."""
    return not model.strip().lower().startswith("gpt-5")


@dataclass(frozen=True)
class Prompt:
    """A versioned instruction text. `sha256` is over `text`, so drift is detectable."""

    name: str
    version: int
    owner: str
    text: str
    sha256: str


@dataclass(frozen=True)
class EgressDecision:
    """What the egress policy did to a prompt on its way to a provider."""

    allowed: bool
    prompt: str
    policy: str
    reason: str = ""


@dataclass(frozen=True)
class OutputVerdict:
    """What the output policy found in a finished narration."""

    ok: bool
    violations: tuple[str, ...] = ()


class BudgetExceeded(Exception):
    """A token ceiling would be crossed. Refuses rather than overspends."""

    def __init__(self, scope: str, limit: int) -> None:
        super().__init__(f"the {scope} token budget of {limit} for today is used up")
        self.scope, self.limit = scope, limit
