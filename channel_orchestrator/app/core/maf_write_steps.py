"""The steps of the write workflow: prepare, wait for the reader, commit. [RM-10b]

    PrepareRequest ─▶ Prepare ─▶ PendingWrite ─▶ AwaitConfirmation ─▶ Approved ─▶ Commit ─▶ CommitOutcome
                                                        ▲
                                          Confirmation (from the reader's exact word)

Three executors and the typed messages between them. What makes this safe is the shape, not a promise:

- **The model reaches `Prepare` and nothing else.** The workflow's only start input is `PrepareRequest`, which
  the model's `*_prepare` tools send (`maf_write_flow.prepare_write`); no tool a model may name starts it any
  other way, and `Commit` accepts only `Approved`, a message only `AwaitConfirmation` creates.
- **`AwaitConfirmation` is the framework's request/response step.** It publishes the preview's request
  (`request_info`) and the workflow goes idle until a `Confirmation` arrives. That reply is produced by the
  orchestrator's own exact-word gate (`writes.parse_command`), for the same person in the same conversation,
  and by nothing a model writes. It checks the expiry with the pipeline's clock.
- **`Commit` sends the commit once** (`writes.send_commit`); the token, the person, the tool, the arguments, the
  expiry and the single use are checked by the gateway and the API exactly as before.

No executor computes: they forward a call, compare an expiry and move a message.
"""
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Executor, WorkflowContext, handler, register_checkpoint_type, response_handler

from app.core import replies
from app.core.gateway_client import GatewayClient, GatewayReply
from app.core.identity import ActingIdentity
from app.core.state import PendingWrite
from app.core.writes import CommitOutcome, send_commit
from application.capabilities import catalog


@dataclass(frozen=True)
class PrepareRequest:
    """What the model's prepare tool asks for: a prepare tool's name and the arguments the rules settled."""

    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Confirmation:
    """The reader's reply to the preview: `confirmed` for the exact confirming words, otherwise a cancel."""

    confirmed: bool


@dataclass(frozen=True)
class Approved:
    """A change that was confirmed in time. Only `AwaitConfirmation` creates one, and only `Commit` accepts it."""

    pending: PendingWrite


for _type in (PrepareRequest, Confirmation, Approved, PendingWrite):
    register_checkpoint_type(_type)


@dataclass
class Prepared:
    """The preview's reply, kept for the model's tool call that started the workflow (the facts stay out of the checkpoint)."""

    reply: GatewayReply | None = None


@dataclass
class WriteContext:
    """What the executors act with: the gateway, the person, the pipeline's clock and the confirmation window.

    `forward` (the turn's one outbound call) and `deadline` (when a preview made now expires) exist only on the
    turn that prepares and are absent on a turn that merely resumes the workflow.
    """

    gateway: GatewayClient
    who: ActingIdentity
    clock: Any
    deadline: Any = None
    forward: Any = None
    prepared: Prepared = field(default_factory=Prepared)


class Prepare(Executor):
    """The model's way in: ask the gateway for a preview as the acting person. Nothing is written."""

    def __init__(self, context: WriteContext) -> None:
        super().__init__(id="prepare")
        self._c = context

    @handler
    async def prepare(self, request: PrepareRequest, ctx: WorkflowContext[PendingWrite]) -> None:
        spec = catalog.BY_NAME[request.tool]
        if spec.kind != catalog.WRITE_PREPARE or self._c.forward is None or self._c.deadline is None:
            raise ValueError(f"{request.tool} is not a preview this workflow may ask for")
        reply = await self._c.forward(spec, request.args)
        self._c.prepared.reply = reply
        pending = PendingWrite.from_preview(request.tool, request.args, reply.body, self._c.deadline()) if reply.ok else None
        if pending is not None:
            await ctx.send_message(pending)


class AwaitConfirmation(Executor):
    """Hold the preview and wait for the reader's reply: the framework's request/response step."""

    def __init__(self, context: WriteContext) -> None:
        super().__init__(id="await_confirmation")
        self._c = context

    @handler
    async def hold(self, pending: PendingWrite, ctx: WorkflowContext) -> None:
        await ctx.request_info(pending, Confirmation)

    @response_handler
    async def answered(self, pending: PendingWrite, reply: Confirmation, ctx: WorkflowContext[Approved, CommitOutcome]) -> None:
        if not reply.confirmed:
            await ctx.yield_output(CommitOutcome(replies.CANCELLED, False))
        elif self._c.clock() >= pending.expires_at:
            await ctx.yield_output(CommitOutcome(replies.EXPIRED, False, pending.tool, "expired"))
        else:
            await ctx.send_message(Approved(pending))


class Commit(Executor):
    """Send the confirmed change's commit, once, as the person who confirmed it."""

    def __init__(self, context: WriteContext) -> None:
        super().__init__(id="commit")
        self._c = context

    @handler
    async def commit(self, approved: Approved, ctx: WorkflowContext[Never, CommitOutcome]) -> None:
        await ctx.yield_output(await send_commit(self._c.gateway, self._c.who, approved.pending))
