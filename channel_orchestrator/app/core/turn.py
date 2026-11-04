"""One turn, start to finish: attribute, decide, run, compose, audit. [CH-08]

    identity → (confirm / cancel?) → (numbered reply?) → tools → compose → reply → audit

- **No identity, no turn.** An unresolved person gets one sentence and nothing runs.
- **Writes.** A model can only prepare (the write workflow, `maf_write_flow`, pauses on the preview); `confirm`
  is handled here, before any model sees the message, and is the only path to `maf_write_flow.commit_pending`,
  which resumes the workflow. Any other message drops a pending change, and the reply says so.
- **Clarify, never guess.** An ambiguous client or a missing year is a question back, with
  the candidates numbered `1) Name`; the next turn's bare number selects one.
- **The reply is composed.** The engine's own blocks, the model's sentence only if the
  numeric guard passes it, the disclaimer, and a provenance footer from the envelopes.
- **A turn has a deadline** (`CHANNEL_TURN_TIMEOUT_SECONDS`). A lost commit answer is reported as
  unknown, never retried.
- **The audit is the last step and never hides the answer** (`audit.NarrationAuditor`).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app.core import replies
from app.core.audit import NarrationAuditor
from app.core.compose import provenance_footer
from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.maf_review_pack import run_review_pack
from app.core.maf_write_flow import cancel_pending, commit_pending, drop_pending
from app.core.planned import Planned
from app.core.planner import Planner
from app.core.review_pack import CALL_LIMIT, MODE, wants_review_pack
from app.core.settings import OrchestratorSettings
from app.core.state import ConversationState, StateStore
from app.core.tools import Clarification, ToolRunner, years_in
from app.core.writes import CommitOutcome, parse_command
from application.composer import Composed
from application.knowledge import render_reference

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
    runs: tuple[Any, ...] = field(default=())


class TurnPipeline:
    """Handles a person's message. One instance serves every conversation; state is per person and conversation."""

    def __init__(
        self, settings: OrchestratorSettings, gateway: GatewayClient, planner: Planner, store: StateStore,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._s, self._gateway, self._planner, self._store, self._clock = settings, gateway, planner, store, clock
        self._auditor = NarrationAuditor(settings, gateway)

    async def handle(self, text: str, who: ActingIdentity | None) -> TurnReply:
        """Answer `text` for `who`, or refuse when nobody can be named."""
        if who is None:
            return TurnReply(replies.UNATTRIBUTED, "refusal")
        state = self._store.get(who.key)
        command = parse_command(text)
        if command:
            return await self._command(command, who, state)
        dropped = await drop_pending(self._gateway, who, state, self._clock)
        reply = await self._respond(text, who, state)
        return replace(reply, text=f"{reply.text}\n\n{replies.DROPPED}") if dropped else reply

    # ------------------------------------------------------------ confirm / cancel

    async def _command(self, command: str, who: ActingIdentity, state: ConversationState) -> TurnReply:
        if command == "cancel":
            had = await cancel_pending(self._gateway, who, state, self._clock)
            return TurnReply(replies.CANCELLED if had else replies.NOTHING_PENDING, "cancel")
        try:
            outcome = await asyncio.wait_for(commit_pending(self._gateway, who, state, self._clock), self._s.turn_timeout_seconds)
        except asyncio.TimeoutError:
            outcome = CommitOutcome(replies.commit_failure("timeout", ""), False, code="timeout")
        state.remember("assistant", outcome.text)
        return TurnReply(outcome.text, "commit" if outcome.made else "commit_refused", tools=(outcome.tool,) if outcome.tool else (),
                         runs=outcome.runs)

    # ------------------------------------------------------------- numbered reply

    async def _respond(self, text: str, who: ActingIdentity, state: ConversationState) -> TurnReply:
        question, chosen = self._select_candidate(text, state)
        if question is None:
            return TurnReply(replies.clarification(Clarification("client", "", tuple(state.candidates))), "clarify")
        try:
            return await asyncio.wait_for(self._answer(question, who, state, chosen), self._s.turn_timeout_seconds)
        except asyncio.TimeoutError:
            log.warning("a turn passed its deadline")
            return TurnReply(replies.TIMED_OUT, "failure")

    def _select_candidate(self, text: str, state: ConversationState) -> tuple[str | None, int | None]:
        """`(question, chosen client)`: the message, or the earlier question once a numbered choice picks its client.

        A number outside the list is not a choice: the question is asked again.
        """
        choices, asked = state.candidates, state.question
        state.candidates, state.question = [], ""
        if not choices and wants_review_pack(asked) and len(text.split()) == 1 and years_in(text):
            return f"{asked} {text.strip()}", None  # the year a pack was waiting for
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
        pack = wants_review_pack(question)
        runner = ToolRunner(
            self._gateway, who, state, question, CALL_LIMIT if pack else self._s.max_tool_calls, self._s.confirm_ttl_seconds,
            self._clock, client_id=chosen,
        )
        planned = await (run_review_pack(runner, self._s.ai.safety.output_allowed_hosts) if pack else self._planner.plan(runner))
        state.remember("user", question)
        if runner.clarify:
            return await self._ask(runner, planned, who, state, question)
        if not runner.runs:
            text = replies.failure(runner.problems) if runner.problems or runner.refused else HELP
            audit = await self._auditor.report(who, planned, runner, None, text)
            return TurnReply(text, "failure" if runner.problems else "help", planned.mode, refused=tuple(runner.refused), audit=audit)
        composed = planned.composed_for(runner)
        text = self._assemble(runner, planned, composed)
        state.write = runner.flow
        state.remember("assistant", text)
        audit = await self._auditor.report(who, planned, runner, composed, text)
        return TurnReply(
            text, "answer", planned.mode, tuple(runner.tool_names), composed.guard.status, composed.narration_used,
            audit, tuple(runner.refused), tuple(runner.runs),
        )

    def _assemble(self, runner: ToolRunner, planned: Planned, composed: Composed) -> str:
        reference = render_reference(planned.reference) if composed.narration_used else ""
        parts = [composed.text, reference, provenance_footer(runner.runs)]
        if planned.model_used and planned.narration and not composed.narration_used:
            parts.append(WITHHELD)
        if planned.degraded:
            parts.append(replies.MODEL_DOWN)
        if runner.problems:
            parts.append(replies.failure(runner.problems))
        if runner.flow is not None:
            parts.append(replies.CONFIRM_HINT)
        if planned.mode == MODE:
            parts.append(replies.REVIEW_PACK_NEXT)
        return "\n\n".join(p for p in parts if p)

    async def _ask(self, runner: ToolRunner, planned: Planned, who: ActingIdentity, state: ConversationState, question: str) -> TurnReply:
        clarify = runner.clarify
        if clarify.kind == "client":
            state.candidates, state.question = [dict(c) for c in clarify.candidates], question
        elif clarify.kind == "year" and wants_review_pack(question):
            state.question = question  # the next message may be just the year
        text = replies.clarification(clarify)
        audit = await self._auditor.report(who, planned, runner, None, text)
        return TurnReply(text, "clarify", planned.mode, tuple(runner.tool_names), audit=audit)

    def status(self) -> dict[str, object]:
        """For `/whoami`: counts and states, never a name, a token or a message."""
        return {"audit_failures": self._auditor.failures, "last_audit_error": self._auditor.last_error or None,
                "conversations": len(self._store)}
