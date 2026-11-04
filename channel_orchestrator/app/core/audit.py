"""The narration report: that a model took part in a turn, and what the guard made of it. [CH-08]

After a turn in which a model was called, the orchestrator tells the gateway, which writes the per-user
trail (`channel_audit` with `action_kind='narrate'` and `tcc_ops.agent_action_audit`). The report holds a
hash of everything the model was sent, the tools that ran, the guard's verdict and a short note: never
the prompt, never the reply. A failure to file it is counted and logged and NEVER hides the answer; the
count and the last error code surface in `/whoami`.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.planned import Planned
from app.core.prompts import narrator_instructions
from app.core.settings import OrchestratorSettings
from app.core.tools import ToolRunner
from application.composer import Composed

log = logging.getLogger("tcc.orchestrator.audit")


def narration_report(
    settings: OrchestratorSettings, who: ActingIdentity, planned: Planned, runner: ToolRunner, composed: Composed | None, text: str,
) -> dict[str, Any]:
    """The body of `POST /channel/v1/audit/narration` for one turn."""
    trace = planned.trace
    _, prompt_version = narrator_instructions()
    rejected = composed is not None and not composed.guard.passed
    return {
        "conversation_id": who.conversation_id[:100], "agent_name": settings.agent_name,
        "agent_version": f"{settings.agent_version}+prompt{prompt_version}"[:50],
        "model": (trace.last.model if trace.last else "")[:100],
        "prompt_sha256": hashlib.sha256("\n".join(trace.prompt_parts).encode("utf-8")).hexdigest(),
        "tool_names": sorted(set(runner.tool_names)),
        "guard_status": "rejected" if rejected else "pass",
        "violations_count": len(composed.guard.violations) if composed and rejected else 0,
        "output_summary": f"mode={planned.mode}; narration_used={bool(composed and composed.narration_used)}; "
                          f"tools={len(runner.runs)}; chars={len(text)}",
    }


class NarrationAuditor:
    """Files narration reports and remembers whether the last one failed."""

    def __init__(self, settings: OrchestratorSettings, gateway: GatewayClient) -> None:
        self._settings, self._gateway = settings, gateway
        self.failures = 0
        self.last_error = ""

    async def report(self, who: ActingIdentity, planned: Planned, runner: ToolRunner, composed: Composed | None, text: str) -> str:
        """`ok`, `failed`, or `skipped` when no model took part. Never raises."""
        if not planned.trace.turns:
            return "skipped"
        reply = await self._gateway.report_narration(who, narration_report(self._settings, who, planned, runner, composed, text))
        if reply.ok:
            self.last_error = ""
            return "ok"
        self.failures += 1
        self.last_error = reply.error_code
        log.error("audit_write_failed source=narration operation=report error_code=%s", reply.error_code)
        return "failed"
