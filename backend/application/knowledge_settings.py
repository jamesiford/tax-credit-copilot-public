"""The knowledge tier's settings: off unless somebody turns it on. [RM-15, ADR-010]

    KNOWLEDGE_ENABLED   false              the master switch; nothing is read or retrieved while it is false
    KNOWLEDGE_PROVIDER  none               none | fake | foundry-iq (only none and fake are implemented)
    KNOWLEDGE_TOP       3                  passages per question, 1 to 10

`foundry-iq` is named so the setting is stable when the adapter exists; asking for it now is a
configuration error that says so, never a silent fall back to nothing (a reader would assume the
reference text they were promised was consulted). A misconfiguration raises at start, like every
other setting here.

Standard library only; vendored into the orchestrator.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from application.knowledge import KnowledgePort
from application.knowledge_fake import FakeKnowledge

log = logging.getLogger(__name__)

PROVIDERS = ("none", "fake", "foundry-iq")
IMPLEMENTED = ("none", "fake")
MAX_TOP = 10


class KnowledgeConfigError(ValueError):
    """The knowledge settings cannot work as written."""


@dataclass(frozen=True)
class KnowledgeSettings:
    """The validated knowledge configuration. The default is the disabled one."""

    enabled: bool = False
    provider: str = "none"
    top: int = 3


def _text(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name) or default).strip()


def _top(env: Mapping[str, str]) -> int:
    raw = _text(env, "KNOWLEDGE_TOP")
    try:
        value = int(raw) if raw else 3
    except ValueError as exc:
        raise KnowledgeConfigError(f"KNOWLEDGE_TOP must be a whole number; got {raw!r}") from exc
    if not 1 <= value <= MAX_TOP:
        raise KnowledgeConfigError(f"KNOWLEDGE_TOP must be between 1 and {MAX_TOP}")
    return value


def load_knowledge_settings(env: Mapping[str, str]) -> KnowledgeSettings:
    """Read and check the environment. Disabled unless KNOWLEDGE_ENABLED is exactly on; a bad value raises."""
    provider = _text(env, "KNOWLEDGE_PROVIDER", "none").lower()
    if provider not in PROVIDERS:
        raise KnowledgeConfigError(f"KNOWLEDGE_PROVIDER must be one of {PROVIDERS}; got {provider!r}")
    enabled = _text(env, "KNOWLEDGE_ENABLED").lower() in ("1", "true", "yes", "on")
    top = _top(env)
    if enabled and provider == "none":
        raise KnowledgeConfigError("KNOWLEDGE_ENABLED is on but KNOWLEDGE_PROVIDER is none: there is nothing to consult")
    if enabled and provider not in IMPLEMENTED:
        raise KnowledgeConfigError(
            f"KNOWLEDGE_PROVIDER={provider} is designed (ADR-010, docs/architecture/KNOWLEDGE-AND-IQ.md) and not implemented"
        )
    return KnowledgeSettings(enabled, provider, top)


def build_knowledge(settings: KnowledgeSettings) -> KnowledgePort | None:
    """The port the settings ask for, or None when the tier is off (the default: nothing is built)."""
    if not settings.enabled:
        return None
    if settings.provider == "fake":
        log.warning("KNOWLEDGE_PROVIDER=fake: reference text comes from a built-in synthetic corpus, not from any statute")
        return FakeKnowledge()
    raise KnowledgeConfigError(f"KNOWLEDGE_PROVIDER={settings.provider} has no implementation")
