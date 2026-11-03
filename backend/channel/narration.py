"""The orchestrator reports each narration here, so a model's involvement is on the record. [CH-08]

The orchestrator composes an answer from the platform's blocks and, optionally, a
model's sentence. Whether that sentence was used is decided there, by the numeric
guard; THIS endpoint is where the decision becomes a durable row per user:

- a `channel_audit` event (`action_kind='narrate'`) carrying the guard outcome, and
- a `tcc_ops.agent_action_audit` row, `is_deterministic_path` true only when the
  guard passed, i.e. every figure in the reply was checked against the tool facts.

The record holds a hash of the prompt and a short note, never the prompt or the
reply. An agent caller only: narration is something the orchestrator does, not
something a Cowork user's token can assert.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from application.agent_audit import AgentInvocation
from application.channel_audit import AuditCall
from channel.auth import Caller

log = logging.getLogger("tcc.channel.narration")

TOOL_NAME = "narration"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NOTE_LIMIT = 400


class NarrationReport(BaseModel):
    """What the orchestrator says about one narration. Unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=100)
    agent_version: str = Field(default="", max_length=50)
    model: str = Field(default="", max_length=100)
    prompt_sha256: str
    tool_names: list[str] = Field(default_factory=list, max_length=20)
    guard_status: Literal["pass", "rejected"]
    violations_count: int = Field(default=0, ge=0, le=10_000)
    output_summary: str = Field(default="", max_length=_NOTE_LIMIT)
    conversation_id: str | None = Field(default=None, max_length=100)

    def problem(self) -> str | None:
        """Why this report cannot be filed, or None."""
        if not _SHA256.match(self.prompt_sha256):
            return "prompt_sha256 must be 64 lowercase hex characters"
        if self.guard_status == "pass" and self.violations_count:
            return "a passed guard cannot report violations"
        return None


class NarrationAudit:
    """Writes the two rows for one narration."""

    def __init__(self, auditor: Any, recorder: Any) -> None:
        self._auditor, self._recorder = auditor, recorder

    def record(self, caller: Caller, report: NarrationReport) -> dict[str, Any]:
        """File the report. Raises only if the channel audit event cannot be written."""
        passed = report.guard_status == "pass"
        call = AuditCall(
            tool_name=TOOL_NAME, action_kind="narrate", actor=caller.acting,
            args={
                "agent_name": report.agent_name, "agent_version": report.agent_version, "model": report.model,
                "prompt_sha256": report.prompt_sha256, "tool_names": sorted(set(report.tool_names)),
                "violations_count": report.violations_count,
            },
            is_deterministic_path=passed,
        )
        audit_id = self._auditor.record_read(
            call, "ok" if passed else "rejected_by_guard", numeric_guard=report.guard_status,
            error=None if passed else f"{report.violations_count} figure(s) not in the tool facts",
        )
        return {"audit_id": audit_id, "agent_action_recorded": self._agent_row(caller, report, passed)}

    def _agent_row(self, caller: Caller, report: NarrationReport, passed: bool) -> bool:
        invocation = AgentInvocation(
            agent_name=report.agent_name, prompt="", output_chars=0, tool_calls=report.tool_names,
            agent_version=report.agent_version or None, model_deployment=report.model or None,
            actor=caller.acting.actor, ok=True, is_deterministic_path=passed,
            prompt_sha256=report.prompt_sha256, intent="channel narration",
            output_note=f"guard={report.guard_status}; violations={report.violations_count}; {report.output_summary}",
        )
        return self._recorder.record(invocation) is not None
