"""The call itself, and what is kept of its answer: the fact ledger and the token strip. [RM-08]

The last function middleware. By the time it runs the arguments are settled and checked, so it only:

1. returns the earlier answer for a call the model repeats (one turn, same tool, same arguments: a second run
   would be a second table);
2. makes the call, once, or once per certified method when the reader did not name one (the statute has not
   chosen between them: each run is labelled by its method, so two runs of one tool never collide on a path);
3. captures what came back: a `ToolRun` into the turn's ledger (the reader's reply is composed from these),
   the conversation's year when the tool ran for one, the prepared write held for its owner's `confirm`
   (the token stays on the turn and is stripped from the facts, so nothing model-visible carries it), and the
   model's answer, which names the facts and never holds a value (`model_answer`, and the lane projection).

The call is the generated tool's body (`maf_catalog_tools.forward_to_gateway`), which returns the gateway's
reply untouched; this module computes, rounds and ranks nothing.
"""
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import FunctionInvocationContext, FunctionMiddleware

from app.core.gateway_client import GatewayReply
from app.core.maf_catalog_tools import TURN
from app.core.maf_tool_rules import answer_with
from app.core.toolset import Problem, ToolRun, lane_diagnostic, method_argument, model_answer
from application.capabilities import catalog
from application.composer import narrator_brief

log = logging.getLogger("tcc.orchestrator.tools")
Next = Callable[[], Awaitable[None]]


def _label(turn: Any, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> str:
    method = args.get(method_argument(spec) or "")
    base = f"{spec.name}_{method}" if isinstance(method, str) else spec.name
    taken = {run.label for run in turn.runs}
    label, n = base, 2
    while label in taken:
        label, n = f"{base}_{n}", n + 1
    return label


def capture(turn: Any, spec: catalog.CapabilitySpec, args: dict[str, Any], reply: GatewayReply) -> dict[str, Any]:
    """Keep one reply in the turn and return what the model may be told of it."""
    if not reply.ok:
        turn.problems.append(Problem(spec.name, reply.error_code, reply.error_message))
        return {"ok": False, "error": reply.error_code, "message": reply.error_message}
    run = ToolRun(spec.name, args, reply.body, _label(turn, spec, args))
    turn.runs.append(run)
    if isinstance(args.get(catalog.TAX_YEAR), int):
        turn.state.tax_year = args[catalog.TAX_YEAR]
    if spec.kind == catalog.WRITE_PREPARE:
        turn.hold(run)
    brief = narrator_brief(turn.question, [spec.name], {run.label: run.model_facts}, notes=list(reply.body.get("warnings") or []))
    answer = model_answer(spec, run, brief)
    log.info("model payload: %s", lane_diagnostic(run, answer))
    return answer


class CallAndCapture(FunctionMiddleware):
    """Makes the call and keeps its answer. Runs last, after every rule has had its say."""

    async def process(self, context: FunctionInvocationContext, call_next: Next) -> None:
        turn, spec = context.kwargs[TURN], catalog.BY_NAME[context.function.name]
        args = dict(context.arguments)
        key = (spec.name, json.dumps(args, sort_keys=True, default=str))
        if key not in turn.answered:  # a repeated call gets the earlier answer, not a second run and a second table
            method = method_argument(spec)
            if method and args.get(method) == "both":
                turn.answered[key] = await self._every_method(context, turn, spec, args, method, call_next)
            else:
                await call_next()
                turn.answered[key] = capture(turn, spec, args, context.result)
        answer_with(context, turn.answered[key])

    async def _every_method(
        self, context: FunctionInvocationContext, turn: Any, spec: catalog.CapabilitySpec, args: dict[str, Any], method: str, call_next: Next,
    ) -> dict[str, Any]:
        """The tool under every certified method, as separate runs: the statute has not chosen between them."""
        answers = []
        for position, certified in enumerate(catalog.CERTIFIED_METHODS):
            if position:
                if turn.calls >= turn.max_calls:
                    break
                turn.calls += 1
            settled = {**args, method: certified}
            context.arguments = settled
            await call_next()
            answers.append(capture(turn, spec, settled, context.result))
        ok = [a for a in answers if a.get("ok")]
        return {"ok": bool(ok), "tool": spec.name, "fact_paths": [p for a in ok for p in a["fact_paths"]], "notes": []}
