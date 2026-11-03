"""One row per narrator-agent invocation, in `tcc_ops.agent_action_audit`. [F3, ADR-008]

The table existed in the DDL and nothing wrote it, so there was no durable record
that a model had been involved in an answer. This writes one row per invocation:
which agent and version, which deployment, a SHA-256 of the prompt (never the
prompt), which capabilities' facts were in the brief, and who asked.

`is_deterministic_path` is TRUE only when every figure in the output was checked
against the facts — the channel's composer does that. The portal chat streams the
model's prose unvalidated, so its rows say FALSE, because anything else would be
a claim the code cannot back.

Recording never changes or interrupts the answer: a failure is logged and the
stream carries on.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from domain.channel import AgentActionAuditRepository, AgentActionAudit, utcnow

log = logging.getLogger("tcc.agent_audit")

_SUMMARY_LIMIT = 2000


@dataclass(frozen=True)
class AgentInvocation:
    """What is known about one agent call, once it has finished."""

    agent_name: str
    prompt: str
    output_chars: int
    tool_calls: Sequence[str] = ()
    agent_version: str | None = None
    model_deployment: str | None = None
    actor: str | None = None
    run_id: str | None = None
    client_id: int | None = None
    intent: str | None = None
    ok: bool = True
    is_deterministic_path: bool = False


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def to_action(invocation: AgentInvocation) -> AgentActionAudit:
    """The row. Summaries say how much, not what: nothing from the prompt or the reply."""
    status = "ok" if invocation.ok else "failed"
    return AgentActionAudit(
        action_id=uuid.uuid4().hex,
        agent_name=invocation.agent_name,
        occurred_at=utcnow(),
        run_id=invocation.run_id,
        client_id=invocation.client_id,
        agent_version=invocation.agent_version,
        model_deployment=invocation.model_deployment,
        prompt_hash=prompt_hash(invocation.prompt),
        tool_calls=json.dumps(sorted(set(invocation.tool_calls))),
        input_summary=f"intent={invocation.intent or 'n/a'}; prompt_chars={len(invocation.prompt)}"[:_SUMMARY_LIMIT],
        output_summary=f"status={status}; output_chars={invocation.output_chars}"[:_SUMMARY_LIMIT],
        user_upn=invocation.actor,
        is_deterministic_path=invocation.is_deterministic_path,
    )


class AgentActionRecorder:
    def __init__(self, repository: AgentActionAuditRepository) -> None:
        self._repository = repository

    def record(self, invocation: AgentInvocation) -> AgentActionAudit | None:
        """Write the row, or log why not. Never raises into the caller's stream."""
        try:
            action = to_action(invocation)
            self._repository.append(action)
            return action
        except Exception:  # noqa: BLE001 - an audit failure must not break an answer
            log.exception("could not record agent action for %s", invocation.agent_name)
            return None
