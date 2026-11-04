"""The state of ONE turn's tools, and the way into the rules for the modes that have no model loop. [CH-08, RM-08]

The model (or the keyword fallback) NAMES a tool and proposes arguments. Everything that decides whose data
it runs on, or whether it runs, is code, and that code is MAF function middleware (`maf_tool_rules`,
`maf_tool_call`), in this order: the budget, the refusal of anything a model may not name, the client
(chosen by code from the reader's words and written over whatever the model passed), the year and the method
(the reader's), the schema check, then the call, then the fact ledger and the token strip. What goes back to
the model is the NAMES of the facts, never their values: a model that has not seen a figure cannot copy it
as a digit. A prepared write's confirmation token is removed from the facts before anyone sees them.

What is left here is the turn itself: the person, the conversation, the budget counter, the results so far
(`runs`, `problems`, `refused`, `clarify`, `pending`), the one gateway call and the resolver call. The
middleware reads and writes this object through `function_invocation_kwargs`; `run` sends one named tool
through the same middleware for the json and keyword modes, which have no model loop of their own.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.gateway_client import GatewayClient, GatewayReply
from app.core.identity import ActingIdentity
from app.core.state import ConversationState, PendingWrite
from app.core.telemetry import tool_span
from app.core.toolset import (  # noqa: F401 - re-exported: the names the rest of the orchestrator imports from here
    Clarification, Problem, ToolRun, first_schema_problem, lane_diagnostic, model_answer, model_tools, numbers_in,
    offered_schema, years_in,
)
from application.capabilities import catalog

log = logging.getLogger("tcc.orchestrator.tools")


@dataclass
class ToolRunner:
    """The tools of ONE turn. Create one per turn; it holds the turn's results and its budget."""

    gateway: GatewayClient
    who: ActingIdentity
    state: ConversationState
    question: str
    max_calls: int
    confirm_ttl_seconds: int
    clock: Callable[[], float] = time.monotonic
    runs: list[ToolRun] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    clarify: Clarification | None = None
    pending: PendingWrite | None = None
    calls: int = 0
    client_id: int | None = None
    answered: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def _timed(self, tool: str, kind: str, args: dict[str, Any]) -> GatewayReply:
        """One gateway call inside a span that carries the tool, its kind and its outcome, and nothing else."""
        with tool_span(tool, kind, self.who.channel, self.who.correlation_id) as span:
            reply = await self.gateway.call_tool(self.who, tool, args)
            span.set_attribute("tcc.outcome", "ok" if reply.ok else "error")
            if not reply.ok:
                span.set_attribute("tcc.error_code", reply.error_code)
        return reply

    async def forward(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> GatewayReply:
        """The generated tools' one outbound call: `spec`'s tool, as the acting person, answered untouched."""
        return await self._timed(spec.name, spec.kind, args)

    def refuse(self, name: str) -> None:
        """Record that a model named a tool it may not call. Nothing ran."""
        self.refused.append(name)
        log.warning("a tool the model may not call was named: %s", name)

    async def ensure_client(self) -> int | None:
        """The one client this turn is about, or None with `clarify` set."""
        if self.client_id is not None or self.clarify is not None:
            return self.client_id
        reply = await self._timed(catalog.CLIENT_RESOLVER, catalog.READ, {
            "name_or_text": self.question, "history": self.state.history, "current_client_id": self.state.client_id,
        })
        if not reply.ok:
            self.problems.append(Problem(catalog.CLIENT_RESOLVER, reply.error_code, reply.error_message))
            return None
        facts = reply.body.get("facts") or {}
        chosen = facts.get("client_id")
        if chosen is None and facts.get("clarify") and len(facts.get("named") or []) == 1:
            chosen = facts["named"][0]  # a gateway that predates `resolved` still asks about one exact name; the reader's own words select
        if chosen is None:
            self.clarify = Clarification("client", str(facts.get("reason") or ""), tuple(facts.get("candidates") or ()))
            return None
        self.client_id = self.state.client_id = int(chosen)
        return self.client_id

    def hold(self, run: ToolRun) -> None:
        """Keep a prepared change for its owner's `confirm`. The token never leaves this object."""
        confirmation = (run.envelope.get("facts") or {}).get("confirmation") or {}
        token = confirmation.get("token")
        if not token:
            self.problems.append(Problem(run.name, "no_confirmation", "the preview carried no confirmation"))
            return
        self.pending = PendingWrite(run.name, dict(run.args), str(token), self.clock() + self.confirm_ttl_seconds)

    async def run(self, name: str, proposed: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run `name` through the turn's rules; return what the MODEL may see (names, never values).

        For the json and keyword modes. A tools-mode turn reaches the same rules through the model's own
        loop and never calls this.
        """
        from app.core.maf_tool_run import run_through_the_rules  # the MAF layer imports this module's types, not the reverse

        return await run_through_the_rules(self, name, dict(proposed or {}))

    @property
    def tool_names(self) -> list[str]:
        return [run.name for run in self.runs]

    def __deepcopy__(self, memo: dict[int, Any]) -> "ToolRunner":
        """A turn is an identity, not a value: the framework deep-copies an agent's default function arguments, and a
        copy would split the budget and the ledger in two while the gateway client holds locks that cannot be copied."""
        return self
