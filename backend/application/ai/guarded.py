"""The outermost guard on a provider: egress, then the token budget. [AI-03, AI-04]

A decorator over `AgentRuntime`, so every provider — Foundry, connection, gateway,
a test fake — passes through the same checks without any of them knowing. The
egress decision is made PER PROVIDER because the same prompt may be allowed to
Foundry and refused to a gateway.

The budget is checked before the call and charged after it: with the provider's own
usage figure when it sent one, otherwise an estimate marked as such. A refusal is
logged and counted but never carries the prompt.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from application.ai.budget import estimate_tokens
from application.ai.ports import AgentRuntime, EgressPolicy, TokenBudget
from domain.ai import (
    AgentSpec, BudgetExceeded, EgressRefused, ModelEvent, ModelUsage, ProviderStatus, TextDelta,
)

log = logging.getLogger(__name__)


def _principal_key() -> str:
    from application.identity import ambient_principal

    principal = ambient_principal()
    return (getattr(principal, "oid", None) or "anonymous") if principal else "anonymous"


class GuardedRuntime:
    """An `AgentRuntime` that checks egress and the token budget before delegating, and charges after."""

    def __init__(
        self, inner: AgentRuntime, egress: EgressPolicy, budget: TokenBudget | None = None,
        telemetry: Any = None,
    ) -> None:
        self._inner, self._egress, self._budget, self._telemetry = inner, egress, budget, telemetry
        self.name = inner.name

    def ready_for(self, agent_name: str) -> bool:
        return self._inner.ready_for(agent_name)

    def version_of(self, agent_name: str) -> str | None:
        return self._inner.version_of(agent_name)

    def status(self) -> ProviderStatus:
        return self._inner.status()

    def _admit(self, principal: str, prompt: str) -> int:
        """Refuse before the call if the day's allowance would be crossed; else the estimate."""
        estimate = estimate_tokens(prompt)
        if self._budget is None:
            return estimate
        try:
            self._budget.check(principal, estimate)
        except BudgetExceeded as exc:
            log.warning("token budget refused a %s call (%s)", self.name, exc.scope)
            if self._telemetry is not None:
                self._telemetry.count("ai.budget_refusals", provider=self.name, scope=exc.scope)
            raise
        return estimate

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        """Egress check, budget check, then the inner stream; charge the budget when it ends."""
        decision = self._egress.prepare(prompt, role=spec.role, provider=self.name)
        if not decision.allowed:
            raise EgressRefused(f"{self.name}: {decision.reason} (policy {decision.policy})")
        principal = _principal_key()
        in_tokens = self._admit(principal, decision.prompt)
        reported, out_chars = None, 0
        try:
            async for event in self._inner.stream(spec, decision.prompt):
                if isinstance(event, ModelUsage):
                    reported = event
                elif isinstance(event, TextDelta):
                    out_chars += len(event.text)
                yield event
        finally:
            if self._budget is not None:
                self._budget.record(principal, reported or ModelUsage(in_tokens, (out_chars + 3) // 4, estimated=True))
