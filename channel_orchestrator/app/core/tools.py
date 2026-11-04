"""Running tools for one turn, inside the turn's rules. [CH-08]

The model (or the keyword fallback) NAMES a tool and proposes arguments. Everything that
decides whose data it runs on, or whether it runs, is code:

- **The client is never the model's.** It is resolved deterministically from the reader's
  words and the conversation (`client_resolve`, the same rule the portal chat follows) and
  written over whatever the model passed. A model that guesses a client id, or a different
  client from the one named, changes nothing.
- **The tax year is the reader's.** A year the model names is used only if the reader said
  it (or it is the conversation's current year); otherwise the reader's single year, the
  conversation's year, or a question back. A hallucinated year cannot select a return.
- **The method is the reader's.** Eligibility is shown under both certified methods unless
  the reader named one, because the statute has not chosen between them.
- **A write can only be PREPARED here.** `*_commit` tools are not in the set a model can
  name; an attempt is refused and recorded, whatever it passes.
- **A budget** (`CHANNEL_MAX_TOOL_CALLS`) bounds how many tools one turn may run.

What goes back to the model is the NAMES of the facts (`narrator_brief`), never their
values: a model that has not seen a figure cannot copy it as a digit. The prepared
write's confirmation token is removed from the facts before anyone sees them.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.state import ConversationState, PendingWrite
from app.core.telemetry import tool_span
from app.core.toolset import (  # noqa: F401 - re-exported: the names the rest of the orchestrator imports from here
    CLIENT_PLACEHOLDER, SCENARIO_NUMBERS, YEAR_KEYS, Clarification, Problem, ToolRun, first_schema_problem, model_answer,
    model_tools, numbers_in, offered_schema, years_in,
)
from application.capabilities import catalog
from application.composer import narrator_brief

log = logging.getLogger("tcc.orchestrator.tools")

_PAY_PERIOD = re.compile(r"pay[\s-]?period", re.IGNORECASE)
_MIN_MAX = re.compile(r"min[\s-]?max", re.IGNORECASE)


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

    # ----------------------------------------------------------------- the client

    async def _timed(self, tool: str, kind: str, args: dict[str, Any]):
        """One gateway call inside a span that carries the tool, its kind and its outcome, and nothing else."""
        with tool_span(tool, kind, self.who.channel, self.who.correlation_id) as span:
            reply = await self.gateway.call_tool(self.who, tool, args)
            span.set_attribute("tcc.outcome", "ok" if reply.ok else "error")
            if not reply.ok:
                span.set_attribute("tcc.error_code", reply.error_code)
        return reply

    async def ensure_client(self) -> int | None:
        """The one client this turn is about, or None with `clarify` set."""
        if self.client_id is not None or self.clarify is not None:
            return self.client_id
        reply = await self._timed("client_resolve", catalog.READ, {
            "name_or_text": self.question, "history": self.state.history, "current_client_id": self.state.client_id,
        })
        if not reply.ok:
            self.problems.append(Problem("client_resolve", reply.error_code, reply.error_message))
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

    # ------------------------------------------------------------------ arguments

    def _year(self, proposed: Any, *, allow_state: bool = True) -> int | None:
        said = years_in(self.question)
        state_year = self.state.tax_year if allow_state else None
        if isinstance(proposed, int) and not isinstance(proposed, bool) and (proposed in said or proposed == state_year):
            return proposed
        return said[0] if len(said) == 1 else state_year

    def _method(self, name: str, proposed: Any) -> str | None:
        if name != "client_eligibility":
            return proposed if isinstance(proposed, str) else None
        pay, minmax = bool(_PAY_PERIOD.search(self.question)), bool(_MIN_MAX.search(self.question))
        return "pay_period" if pay and not minmax else "min_max" if minmax and not pay else "both"

    def _years(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> bool:
        """Settle every year argument from the reader's words; False (with `clarify` set) when a needed one is missing."""
        for key in (k for k in YEAR_KEYS if k in spec.schema["properties"]):
            explicit_only = spec.kind == catalog.WRITE_PREPARE or key == "base_year"
            year = self._year(args.get(key), allow_state=not explicit_only)
            if year is not None:
                args[key] = year
            elif key in spec.schema.get("required", []) or spec.needs_year:
                self.clarify = self.clarify or Clarification("year", "no tax year was named")
                return False
            else:
                args.pop(key, None)
        return True

    def _scenario(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> bool:
        """A what-if's numbers are the reader's: one the model chose is dropped, and a missing size is asked for."""
        said = numbers_in(self.question)
        for key in SCENARIO_NUMBERS:
            if key in args and not (isinstance(args[key], (int, float)) and float(args[key]) in said):
                del args[key]
        if "magnitude" in spec.schema["properties"] and "magnitude" not in args:
            self.clarify = self.clarify or Clarification("detail", "How many, or by how much?")
            return False
        return True

    def _tax_years(self, args: dict[str, Any]) -> None:
        """A data tool's years are the reader's, like every other year: a year the model named that the
        reader did not say (and the conversation is not on) is replaced by the years they did say, or
        dropped, which means every year the data holds. A model cannot select a return by guessing."""
        proposed, said = args.pop("tax_years", None), years_in(self.question)
        allowed = {*said, *([self.state.tax_year] if self.state.tax_year else [])}
        if isinstance(proposed, dict) and all(isinstance(proposed.get(k), int) and proposed[k] in allowed for k in ("from", "to")):
            args["tax_years"] = proposed
            return
        kept = [y for y in proposed if isinstance(y, int) and y in allowed] if isinstance(proposed, list) else []
        if kept or said:
            args["tax_years"] = kept or said

    async def _arguments(self, spec: catalog.CapabilitySpec, proposed: dict[str, Any]) -> dict[str, Any] | None:
        args = {k: v for k, v in proposed.items() if v is not None}
        properties = spec.schema["properties"]
        if CLIENT_PLACEHOLDER in properties:
            client = await self.ensure_client()
            if client is None:
                return None
            args[CLIENT_PLACEHOLDER] = client
        if "tax_years" in properties:
            self._tax_years(args)
        if not self._years(spec, args) or not self._scenario(spec, args):
            return None
        if "method" in properties:
            method = self._method(spec.name, args.get("method"))
            if method is None:
                args.pop("method", None)
            else:
                args["method"] = method
        return args

    # -------------------------------------------------------------------- running

    async def run(self, name: str, proposed: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run `name` if the rules allow; return what the MODEL may see (names, never values)."""
        spec = model_tools().get(name)
        if spec is None:
            self.refused.append(name)
            log.warning("a tool the model may not call was named: %s", name)
            return {"ok": False, "error": "unknown_tool", "message": f"{name} is not a tool you may call"}
        if self.calls >= self.max_calls:
            return {"ok": False, "error": "tool_budget", "message": "no more tools may run in this turn"}
        self.calls += 1
        args = await self._arguments(spec, dict(proposed or {}))
        if args is None:
            what = self.clarify.kind if self.clarify else "client"
            return {"ok": False, "error": "needs_" + what, "message": f"the reader must say which {what} (or how much); stop and wait"}
        invalid = first_schema_problem(spec, args)
        if invalid:
            self.problems.append(Problem(name, "invalid_arguments", invalid))
            return {"ok": False, "error": "invalid_arguments", "message": invalid}
        if args.get("method") == "both":
            return await self._both_methods(spec, args)
        return await self._call(spec, args)

    async def _both_methods(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> dict[str, Any]:
        """Eligibility under both certified methods, as two runs: the statute has not chosen between them."""
        answers = []
        for position, method in enumerate(("min_max", "pay_period")):
            if position:
                if self.calls >= self.max_calls:
                    break
                self.calls += 1
            answers.append(await self._call(spec, {**args, "method": method}))
        ok = [a for a in answers if a.get("ok")]
        return {"ok": bool(ok), "tool": spec.name, "fact_paths": [p for a in ok for p in a["fact_paths"]], "notes": []}

    def _label(self, name: str, args: dict[str, Any]) -> str:
        base = f"{name}_{args['method']}" if isinstance(args.get("method"), str) else name
        taken = {run.label for run in self.runs}
        label, n = base, 2
        while label in taken:
            label, n = f"{base}_{n}", n + 1
        return label

    async def _call(self, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> dict[str, Any]:
        reply = await self._timed(spec.name, spec.kind, args)
        if not reply.ok:
            self.problems.append(Problem(spec.name, reply.error_code, reply.error_message))
            return {"ok": False, "error": reply.error_code, "message": reply.error_message}
        run = ToolRun(spec.name, args, reply.body, self._label(spec.name, args))
        self.runs.append(run)
        if isinstance(args.get("tax_year"), int):
            self.state.tax_year = args["tax_year"]
        if spec.kind == catalog.WRITE_PREPARE:
            self._hold(run)
        brief = narrator_brief(self.question, [spec.name], {run.label: run.model_facts}, notes=list(reply.body.get("warnings") or []))
        return model_answer(spec, run, brief)

    def _hold(self, run: ToolRun) -> None:
        """Keep a prepared change for its owner's `confirm`. The token never leaves this object."""
        confirmation = (run.envelope.get("facts") or {}).get("confirmation") or {}
        token = confirmation.get("token")
        if not token:
            self.problems.append(Problem(run.name, "no_confirmation", "the preview carried no confirmation"))
            return
        self.pending = PendingWrite(run.name, dict(run.args), str(token), self.clock() + self.confirm_ttl_seconds)

    @property
    def tool_names(self) -> list[str]:
        return [run.name for run in self.runs]


