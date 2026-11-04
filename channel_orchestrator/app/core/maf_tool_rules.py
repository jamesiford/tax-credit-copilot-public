"""The turn's tool rules, as MAF function middleware, in the order they run. [RM-08]

    budget → refusal → client → year and method → schema check → (call and capture: `maf_tool_call`)

Each rule is a `FunctionMiddleware` that reads the turn from `function_invocation_kwargs` (so the rules, like
the generated tools, are built once and carry nothing) and either lets the call go on or answers it itself with
a stable code and one sentence. None of them computes a figure; the guarantees they keep are these:

- **A budget** bounds how many tools one turn may run (`max_function_calls` on the chat client is only the
  framework's best-effort backstop: it is checked after a batch, not before a call).
- **A tool a model may not call never runs.** A commit is not in the model's set. The framework answers an
  unregistered name before any function middleware (finding F-03), so `RecordUnregisteredCalls` is CHAT
  middleware that sees the model's reply, records the attempt in `refused` and lets the framework say "not
  found"; `RefuseUnlisted` is the same rule one level down, in case a tool is ever registered by mistake.
- **The client is never the model's.** It is resolved from the reader's words and written over whatever the
  model passed. The tax year and the method are the reader's too (`reader_arguments.ReaderWords`).
- **The schema is the catalog's.** The framework checks a mapping schema only shallowly (finding F-04), so
  `jsonschema` checks the settled arguments against the catalog's strict schema.

Which arguments a tool holds that are the reader's is `CapabilitySpec.reader_owned`; no argument is named here.
"""
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import ChatContext, ChatMiddleware, FunctionInvocationContext, FunctionMiddleware

from app.core.maf_catalog_tools import TURN
from app.core.reader_arguments import ReaderWords
from app.core.toolset import Problem, first_schema_problem, model_tools, needs_reader, refusal
from application.capabilities import catalog
from application.capabilities.catalog_types import OWNED_CLIENT, OWNED_METHOD, OWNED_METHOD_BOTH, OWNED_YEARS

log = logging.getLogger("tcc.orchestrator.rules")
Next = Callable[[], Awaitable[None]]


def answer_with(context: FunctionInvocationContext, answer: dict[str, Any]) -> None:
    """Answer the call without running it: what the model reads is the JSON of `answer`."""
    context.result = json.dumps(answer, default=str)


class Budget(FunctionMiddleware):
    """First: a turn may run `max_calls` tools. A call over the budget is refused, and an allowed one is counted."""

    async def process(self, context: FunctionInvocationContext, call_next: Next) -> None:
        turn = context.kwargs[TURN]
        if turn.calls >= turn.max_calls:
            return answer_with(context, refusal("tool_budget", "no more tools may run in this turn"))
        turn.calls += 1
        await call_next()


class RefuseUnlisted(FunctionMiddleware):
    """A tool a model may not name is refused and recorded, whatever it passes. A commit is never in that set."""

    async def process(self, context: FunctionInvocationContext, call_next: Next) -> None:
        name = context.function.name
        if name in model_tools():
            return await call_next()
        context.kwargs[TURN].refuse(name)
        answer_with(context, refusal("unknown_tool", f"{name} is not a tool you may call"))


class ClientFromReader(FunctionMiddleware):
    """The client is chosen by code and written over whatever the model passed; a null the model sent is dropped."""

    async def process(self, context: FunctionInvocationContext, call_next: Next) -> None:
        turn, spec = context.kwargs[TURN], catalog.BY_NAME[context.function.name]
        args = {k: v for k, v in dict(context.arguments).items() if v is not None}
        for owned in spec.owned(OWNED_CLIENT):
            client = await turn.ensure_client()
            if client is None:
                return answer_with(context, needs_reader(turn.clarify))
            args[owned.name] = client
        context.arguments = args
        await call_next()


class YearAndMethodFromReader(FunctionMiddleware):
    """The tax year, a what-if's numbers and the method are the reader's words, never the model's guess."""

    async def process(self, context: FunctionInvocationContext, call_next: Next) -> None:
        turn, spec = context.kwargs[TURN], catalog.BY_NAME[context.function.name]
        args, words = dict(context.arguments), ReaderWords(turn.question, turn.state.tax_year)
        for owned in spec.owned(OWNED_YEARS):
            words.tax_years(owned.name, args)
        asked = words.years(spec, args) or words.scenario(spec, args)
        if asked:
            turn.clarify = turn.clarify or asked
            return answer_with(context, needs_reader(turn.clarify))
        for owned in spec.owned(OWNED_METHOD, OWNED_METHOD_BOTH):
            method = words.method(owned.kind, args.get(owned.name))
            if method is None:
                args.pop(owned.name, None)
            else:
                args[owned.name] = method
        context.arguments = args
        await call_next()


class SchemaCheck(FunctionMiddleware):
    """The settled arguments must fit the catalog's own strict schema; a call that does not is not made."""

    async def process(self, context: FunctionInvocationContext, call_next: Next) -> None:
        turn, spec = context.kwargs[TURN], catalog.BY_NAME[context.function.name]
        invalid = first_schema_problem(spec, dict(context.arguments))
        if invalid:
            turn.problems.append(Problem(spec.name, "invalid_arguments", invalid))
            return answer_with(context, refusal("invalid_arguments", invalid))
        await call_next()


class RecordUnregisteredCalls(ChatMiddleware):
    """Records each tool name the model asked for that is not registered (a commit, an invented name).

    Function middleware never sees such a call, so the attempt is read from the model's reply. The framework
    still answers it ("not found"); nothing is registered to refuse it, because a stub for a commit would
    put the commit in the model's set.
    """

    def __init__(self, turn: Any) -> None:
        self._turn = turn

    async def process(self, context: ChatContext, call_next: Next) -> None:
        await call_next()
        known = {t.name for t in (context.options or {}).get("tools") or []}
        for message in getattr(context.result, "messages", None) or []:
            for content in message.contents:
                if content.type == "function_call" and content.name not in known:
                    self._turn.refuse(content.name)


def tool_rules() -> list[FunctionMiddleware]:
    """The rules ahead of the call, in order. The call itself (`CallAndCapture`) is added after them."""
    return [Budget(), RefuseUnlisted(), ClientFromReader(), YearAndMethodFromReader(), SchemaCheck()]
