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

from jsonschema import Draft202012Validator

from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.state import ConversationState, PendingWrite
from application.capabilities import catalog
from application.composer import narrator_brief

log = logging.getLogger("tcc.orchestrator.tools")

_YEAR = re.compile(r"\b(?:ty\s?)?((?:19|20)\d\d)\b", re.IGNORECASE)
_PAY_PERIOD = re.compile(r"pay[\s-]?period", re.IGNORECASE)
_MIN_MAX = re.compile(r"min[\s-]?max", re.IGNORECASE)
_NOT_FOR_MODELS = frozenset({"client_resolve", "employee_drill"})
CLIENT_PLACEHOLDER = "client_id"


def model_tools() -> dict[str, catalog.CapabilitySpec]:
    """The tools a model may name: built reads and previews, never a commit, never plumbing."""
    return {
        spec.name: spec for spec in catalog.offered()
        if spec.kind != catalog.WRITE_COMMIT and not {catalog.GATEWAY_LOCAL, catalog.INTERNAL} & set(spec.tags)
        and spec.name not in _NOT_FOR_MODELS
    }


def years_in(text: str) -> list[int]:
    """Every four-digit year in `text`, in order, without repeats."""
    found: list[int] = []
    for match in _YEAR.finditer(text or ""):
        year = int(match.group(1))
        if year not in found:
            found.append(year)
    return found


def offered_schema(spec: catalog.CapabilitySpec) -> dict[str, Any]:
    """The schema a model is shown: the client and the year are not the model's to supply.

    The client is written in by the runner; a year is used only if the reader said it. Neither is
    `required` here, so a call that omits them reaches the runner, which asks the reader, rather
    than being bounced back to the model to guess. Extra properties are tolerated at this door and
    judged by the runner against the catalog's own strict schema, so a client id the model invents
    reaches the one place that overwrites it.
    """
    schema = {**spec.schema, "properties": {k: v for k, v in spec.schema["properties"].items() if k != CLIENT_PLACEHOLDER}}
    schema["required"] = [name for name in spec.schema.get("required", []) if name not in (CLIENT_PLACEHOLDER, "tax_year", "year")]
    schema["additionalProperties"] = True
    return schema


@dataclass(frozen=True)
class ToolRun:
    """One tool that ran and answered: its name, the arguments used, the gateway's envelope and its label.

    The `label` namespaces the run's facts in the composed reply (`client_eligibility_min_max`),
    so the same tool run under two methods never collides on a path.
    """

    name: str
    args: dict[str, Any]
    envelope: dict[str, Any]
    label: str = ""

    @property
    def facts(self) -> dict[str, Any]:
        """The envelope's facts without the confirmation token, which only the owner's `confirm` may use."""
        return {k: v for k, v in (self.envelope.get("facts") or {}).items() if k != "confirmation"}


@dataclass(frozen=True)
class Clarification:
    """What the reader must say before anything can run. `candidates` are numbered in the reply."""

    kind: str
    reason: str = ""
    candidates: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Problem:
    """A tool that did not answer, in words that are safe to show."""

    tool: str
    code: str
    message: str


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

    async def ensure_client(self) -> int | None:
        """The one client this turn is about, or None with `clarify` set."""
        if self.client_id is not None or self.clarify is not None:
            return self.client_id
        reply = await self.gateway.call_tool(self.who, "client_resolve", {
            "name_or_text": self.question, "history": self.state.history, "current_client_id": self.state.client_id,
        })
        if not reply.ok:
            self.problems.append(Problem("client_resolve", reply.error_code, reply.error_message))
            return None
        facts = reply.body.get("facts") or {}
        chosen = facts.get("client_id")
        if chosen is None and facts.get("clarify") and len(facts.get("named") or []) == 1:
            chosen = facts["named"][0]  # Teams has no page selection: one name, in the reader's own words, selects
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

    async def _arguments(self, spec: catalog.CapabilitySpec, proposed: dict[str, Any]) -> dict[str, Any] | None:
        args = {k: v for k, v in proposed.items() if v is not None}
        properties = spec.schema["properties"]
        if CLIENT_PLACEHOLDER in properties:
            client = await self.ensure_client()
            if client is None:
                return None
            args[CLIENT_PLACEHOLDER] = client
        for key in ("tax_year", "year"):
            if key not in properties:
                continue
            year = self._year(args.get(key), allow_state=spec.kind != catalog.WRITE_PREPARE)
            if year is None:
                if key in spec.schema.get("required", []) or spec.needs_year:
                    self.clarify = self.clarify or Clarification("year", "no tax year was named")
                    return None
                args.pop(key, None)
            else:
                args[key] = year
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
            what = "year" if self.clarify and self.clarify.kind == "year" else "client"
            return {"ok": False, "error": "needs_" + what, "message": f"the reader must say which {what}; stop and wait"}
        invalid = _first_schema_problem(spec, args)
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
        reply = await self.gateway.call_tool(self.who, spec.name, args)
        if not reply.ok:
            self.problems.append(Problem(spec.name, reply.error_code, reply.error_message))
            return {"ok": False, "error": reply.error_code, "message": reply.error_message}
        run = ToolRun(spec.name, args, reply.body, self._label(spec.name, args))
        self.runs.append(run)
        if isinstance(args.get("tax_year"), int):
            self.state.tax_year = args["tax_year"]
        if spec.kind == catalog.WRITE_PREPARE:
            self._hold(run)
        brief = narrator_brief(self.question, [spec.name], {run.label: run.facts}, notes=list(reply.body.get("warnings") or []))
        return {"ok": True, "tool": spec.name, "fact_paths": brief["fact_paths"], "notes": brief["notes"]}

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


def _first_schema_problem(spec: catalog.CapabilitySpec, args: dict[str, Any]) -> str | None:
    errors = sorted(Draft202012Validator(spec.schema).iter_errors(args), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    return "; ".join(f"{'.'.join(str(p) for p in e.absolute_path) or 'arguments'}: {e.message}" for e in errors[:3])
