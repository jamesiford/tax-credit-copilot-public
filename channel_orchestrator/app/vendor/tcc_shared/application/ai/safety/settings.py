"""Safety switches. [AI-07]

    AI_INJECTION_GUARD         on     on | off — refuse to send a prompt carrying an instruction-override attempt
    AI_OUTPUT_POLICY           on     on | off — withhold prose that breaks an output rule
    AI_OUTPUT_ALLOWED_HOSTS    (none) comma-separated host suffixes the model may link to

Both guards default ON and an `off` is logged at startup: they are controls, and a
control that is silently off reads as one that is on. `off` exists for a false
positive in production while the rule is fixed, not as a configuration to leave.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SafetySettings:
    """Which safety controls are on, and the link allow-list for model prose."""

    injection_guard: bool = True
    output_policy: bool = True
    output_allowed_hosts: tuple[str, ...] = ()

    @property
    def disabled_controls(self) -> tuple[str, ...]:
        return tuple(name for name, on in (("injection_guard", self.injection_guard), ("output_policy", self.output_policy)) if not on)


def _switch(env: Mapping[str, Any], name: str) -> bool:
    raw = str(env.get(name) or "on").strip().lower()
    if raw not in {"on", "off"}:
        from application.ai.settings import AiConfigurationError

        raise AiConfigurationError(f"{name} must be 'on' or 'off'; got {raw!r}")
    return raw == "on"


def load_safety_settings(env: Mapping[str, Any]) -> SafetySettings:
    hosts = tuple(h.strip().lower() for h in str(env.get("AI_OUTPUT_ALLOWED_HOSTS") or "").split(",") if h.strip())
    return SafetySettings(_switch(env, "AI_INJECTION_GUARD"), _switch(env, "AI_OUTPUT_POLICY"), hosts)
