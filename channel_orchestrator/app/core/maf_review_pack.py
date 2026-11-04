"""The client review pack as a MAF Workflow: resolve, read the position, check, compose. [RM-10c]

    PackRequest ─▶ ResolveClient ─▶ one step per capability ─▶ Check ─▶ Compose

A fixed sequence is a Workflow, not an Agent (`review_pack` says what it runs and what it leaves out). Every step is
the same thing: a call to one catalog capability through the turn's rules (`ToolRunner.run`: the budget, the
client, the year and the method, the schema, the fact ledger), which is the generated tool and the function
middleware an Agent's loop uses, ending in the same gateway call as the person asking. The steps keep the
results in the turn's ledger; the last one composes the reply from the engine's own blocks with the verbatim
composer and the numeric guard (`Planned.composed_for`), with no narration: no model takes part.

**No executor computes.** They move a marker from one step to the next and stop the sequence when the reader must
say something (a client, a year) or when nothing answered. Every figure in the reply is a tool's.
"""
import logging
from dataclasses import dataclass
from typing import Any, Never

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from app.core.planned import Planned
from app.core.review_pack import MODE, step_tools
from application.composer import Composed

log = logging.getLogger("tcc.orchestrator.review_pack")
NAME = "tcc-review-pack"


@dataclass(frozen=True)
class PackRequest:
    """The reader's request for the pack."""

    question: str


@dataclass(frozen=True)
class Carry:
    """The sequence goes on."""


@dataclass(frozen=True)
class Stopped:
    """The sequence ended early: `client` or `ask` (the reader must say something) or `nothing` (no step answered)."""

    reason: str


class ResolveClient(Executor):
    """The first step: the one client the pack is about, chosen by code, or a question back."""

    def __init__(self, turn: Any) -> None:
        super().__init__(id="resolve_client")
        self._turn = turn

    @handler
    async def resolve(self, request: PackRequest, ctx: WorkflowContext[Carry, Stopped]) -> None:
        if await self._turn.ensure_client() is None:
            await ctx.yield_output(Stopped("client"))
        else:
            await ctx.send_message(Carry())


class Capability(Executor):
    """One calculation: a catalog capability, run through the turn's rules and kept in its ledger."""

    def __init__(self, turn: Any, tool: str) -> None:
        super().__init__(id=f"step_{tool}")
        self._turn, self._tool = turn, tool

    @handler
    async def run(self, carry: Carry, ctx: WorkflowContext[Carry, Stopped]) -> None:
        await self._turn.run(self._tool, {})
        if self._turn.clarify is not None:
            await ctx.yield_output(Stopped("ask"))
        else:
            await ctx.send_message(Carry())


class Check(Executor):
    """Before composing: something must have answered. A step that failed is already in the turn's `problems`."""

    def __init__(self, turn: Any) -> None:
        super().__init__(id="check")
        self._turn = turn

    @handler
    async def check(self, carry: Carry, ctx: WorkflowContext[Carry, Stopped]) -> None:
        if not self._turn.runs:
            await ctx.yield_output(Stopped("nothing"))
        else:
            await ctx.send_message(carry)


class Compose(Executor):
    """The last step: the reply from the engine's own blocks, through the composer and the numeric guard."""

    def __init__(self, turn: Any, planned: Planned) -> None:
        super().__init__(id="compose")
        self._turn, self._planned = turn, planned

    @handler
    async def compose(self, carry: Carry, ctx: WorkflowContext[Never, Composed]) -> None:
        await ctx.yield_output(self._planned.composed_for(self._turn))


def build_pack_flow(turn: Any, planned: Planned) -> Workflow:
    """The pack's graph: one chain, resolve to compose, a step per tool `review_pack.step_tools` names."""
    steps = [Capability(turn, tool) for tool in step_tools()]
    first = ResolveClient(turn)
    return (
        WorkflowBuilder(start_executor=first, name=NAME, output_from="all")
        .add_chain([first, *steps, Check(turn), Compose(turn, planned)]).build()
    )


async def run_review_pack(turn: Any, hosts: tuple[str, ...] = ()) -> Planned:
    """Run the pack for `turn`. What it found is in the turn's ledger; the composed reply is on the result.

    A framework fault is logged and leaves whatever ran in the ledger; the reply is then composed from that.
    """
    planned = Planned(MODE, hosts=hosts)
    try:
        await build_pack_flow(turn, planned).run(PackRequest(turn.question))
    except Exception as exc:  # noqa: BLE001 - whatever the framework does, the reader still gets what the tools returned
        log.warning("the review pack workflow failed (%s); answering from what ran", type(exc).__name__)
    return planned
