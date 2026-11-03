"""One turn, start to finish: attribute, decide, run, compose, audit. [CH-08]

    identity → (confirm / cancel?) → (numbered reply?) → tools → compose → reply → audit

- **No identity, no turn.** An unresolved person gets one sentence and nothing runs.
- **Writes.** A model can only prepare; `confirm` is handled here, before any model sees
  the message, and is the only path to `writes.commit_pending`.
- **Clarify, never guess.** An ambiguous client or a missing year is a question back, with
  the candidates numbered; the next turn's bare number selects one.
- **The reply is composed.** The engine's own blocks, the model's sentence only if the
  numeric guard passes it, the disclaimer, and a provenance footer from the envelopes.
- **The audit is the last step and never hides the answer.** The narration report is
  filed with the gateway, which writes the per-user trail; if that fails the reply still
  goes out, the failure is logged, and `/whoami` reports the count.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core import replies
from app.core.compose import compose_reply, provenance_footer
from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.planner import Planned, Planner
from app.core.prompts import narrator_instructions
from app.core.settings import OrchestratorSettings
from app.core.state import ConversationState, StateStore
from app.core.tools import Clarification, ToolRunner
from app.core.writes import commit_pending, parse_command
from application.composer import Composed

log = logging.getLogger("tcc.orchestrator.turn")

HELP = (
    "I can answer from the platform's calculations: who to call across the book, one client's "
    "situation, eligibility and credit for a tax year, trend since the base year, jobs at risk of "
    "falling out, other programmes, what-ifs and the calculation walk-through. Ask about a client by name."
)
WITHHELD = "_The commentary was withheld because it could not be verified against the engine's figures._"


@dataclass(frozen=True)
class TurnReply:
    """What goes back to the reader, and what the turn did (for tests and `/whoami`)."""

    text: str
    kind: str
    mode: str = "none"
    tools: tuple[str, ...] = ()
    guard_status: str = "n/a"
    narration_used: bool = False
    audit: str = "skipped"
    refused: tuple[str, ...] = field(default=())


class TurnPipeline:
    """Handles a person's message. One instance serves every conversation; state is per person and conversation."""

    def __init__(
        self, settings: OrchestratorSettings, gateway: GatewayClient, planner: Planner, store: StateStore,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._s, self._gateway, self._planner, self._store, self._clock = settings, gateway, planner, store, clock
        self.audit_failures = 0
        self.last_audit_error = ""

    async def handle(self, text: str, who: ActingIdentity | None) -> TurnReply:
        """Answer `text` for `who`, or refuse when nobody can be named."""
        if who is None:
            return TurnReply(replies.UNATTRIBUTED, "refusal")
        state = self._store.get(who.key)
        command = parse_command(text)
        if command:
            return await self._command(command, who, state)
        state.pending = None
        question, chosen = self._select_candidate(text, state)
        if question is None:
            return TurnReply(replies.clarification(Clarification("client", "", tuple(state.candidates))), "clarify")
        return await self._answer(question, who, state, chosen)

    # ------------------------------------------------------------ confirm / cancel

    async def _command(self, command: str, who: ActingIdentity, state: ConversationState) -> TurnReply:
        if command == "cancel":
            had = state.pending is not None
            state.pending = None
            return TurnReply(replies.CANCELLED if had else replies.NOTHING_PENDING, "cancel")
        outcome = await commit_pending(self._gateway, who, state, self._clock)
        state.remember("assistant", outcome.text)
        return TurnReply(outcome.text, "commit" if outcome.made else "commit_refused", tools=(outcome.tool,) if outcome.tool else ())

    # ------------------------------------------------------------- numbered reply

    def _select_candidate(self, text: str, state: ConversationState) -> tuple[str | None, int | None]:
        """`(question, chosen client)`: the message, or the earlier question once a numbered choice picks its client.

        A number outside the list is not a choice: the question is asked again.
        """
        choices, asked = state.candidates, state.question
        state.candidates, state.question = [], ""
        if not choices or not text.strip().isdigit():
            return text, None
        index = int(text.strip())
        if not 1 <= index <= len(choices):
            state.candidates, state.question = choices, asked
            return None, None
        chosen = int(choices[index - 1]["client_id"])
        state.client_id = chosen
        return asked or text, chosen

    # --------------------------------------------------------------------- answer

    async def _answer(self, question: str, who: ActingIdentity, state: ConversationState, chosen: int | None) -> TurnReply:
        runner = ToolRunner(
            self._gateway, who, state, question, self._s.max_tool_calls, self._s.confirm_ttl_seconds, self._clock,
            client_id=chosen,
        )
        planned = await self._planner.plan(runner)
        state.remember("user", question)
        if runner.clarify:
            return await self._ask(runner, planned, who, state, question)
        if not runner.runs:
            text = replies.failure(runner.problems) if runner.problems or runner.refused else HELP
            kind = "failure" if runner.problems else "help"
            audit = await self._audit(who, runner, planned, None, text)
            return TurnReply(text, kind, planned.mode, refused=tuple(runner.refused), audit=audit)
        composed = planned.composed or compose_reply(question, runner.runs, planned.narration, self._s.ai.safety.output_allowed_hosts)
        text = self._assemble(runner, planned, composed)
        state.pending = runner.pending
        state.remember("assistant", text)
        audit = await self._audit(who, runner, planned, composed, text)
        return TurnReply(
            text, "answer", planned.mode, tuple(runner.tool_names), composed.guard.status, composed.narration_used,
            audit, tuple(runner.refused),
        )

    def _assemble(self, runner: ToolRunner, planned: Planned, composed: Composed) -> str:
        parts = [composed.text, provenance_footer(runner.runs)]
        if planned.model_used and planned.narration and not composed.narration_used:
            parts.append(WITHHELD)
        if planned.degraded:
            parts.append(replies.MODEL_DOWN)
        if runner.problems:
            parts.append(replies.failure(runner.problems))
        if runner.pending is not None:
            parts.append(replies.CONFIRM_HINT)
        return "\n\n".join(p for p in parts if p)

    async def _ask(self, runner: ToolRunner, planned: Planned, who: ActingIdentity, state: ConversationState, question: str) -> TurnReply:
        clarify = runner.clarify
        if clarify.kind == "client":
            state.candidates, state.question = [dict(c) for c in clarify.candidates], question
        text = replies.clarification(clarify)
        audit = await self._audit(who, runner, planned, None, text)
        return TurnReply(text, "clarify", planned.mode, tuple(runner.tool_names), audit=audit)

    # ---------------------------------------------------------------------- audit

    async def _audit(self, who: ActingIdentity, runner: ToolRunner, planned: Planned, composed: Composed | None, text: str) -> str:
        """Report the narration to the gateway when a model took part. Returns `ok`, `failed` or `skipped`; never raises."""
        trace = planned.trace
        if not trace.turns:
            return "skipped"
        _, prompt_version = narrator_instructions()
        rejected = composed is not None and not composed.guard.passed
        report = {
            "agent_name": self._s.agent_name, "agent_version": f"{self._s.agent_version}+prompt{prompt_version}"[:50],
            "model": (trace.last.model if trace.last else "")[:100],
            "prompt_sha256": hashlib.sha256("\n".join(trace.prompt_parts).encode("utf-8")).hexdigest(),
            "tool_names": sorted(set(runner.tool_names)),
            "guard_status": "rejected" if rejected else "pass",
            "violations_count": len(composed.guard.violations) if composed and rejected else 0,
            "output_summary": f"mode={planned.mode}; narration_used={bool(composed and composed.narration_used)}; "
                              f"tools={len(runner.runs)}; chars={len(text)}",
        }
        reply = await self._gateway.report_narration(who, report)
        if reply.ok:
            self.last_audit_error = ""
            return "ok"
        self.audit_failures += 1
        self.last_audit_error = reply.error_code
        log.error("narration audit failed: %s", reply.error_code)
        return "failed"

    def status(self) -> dict[str, object]:
        """For `/whoami`: counts and states, never a name, a token or a message."""
        return {"audit_failures": self.audit_failures, "last_audit_error": self.last_audit_error or None, "conversations": len(self._store)}
