"""The write path as a MAF Workflow: build it, start it from a prepare, resume it from the reader's word. [RM-10b]

`maf_write_steps` holds the three steps. This module is how the orchestrator uses them:

- `prepare_write` is the body of every `*_prepare` tool a model may name. It starts a fresh workflow, which asks
  the gateway for the preview and pauses on the framework's request step; the paused workflow (an in-memory
  checkpoint) is put on the turn, and the preview's reply is returned to the tool loop untouched.
- `commit_pending` is called from `TurnPipeline`, after the exact-word gate, for the person's `confirm`. It
  rebuilds the graph and resumes it from the checkpoint with a `Confirmation`; the commit executor runs only
  then, as the person who confirmed.
- `cancel_pending` resumes it with a refusal; `drop_pending` cancels the request, for any other message.

**Persistence.** The graph is built fresh on every run and resumes from `InMemoryCheckpointStorage`, one per
paused write. The checkpoint holds the single-use token, so it must not reach a disk or a store another replica
can read (D-81: the container's filesystem may be discarded and replicas are interchangeable). A restart
therefore loses a pending confirmation exactly as before: it cannot be confirmed, and the person asks again.
The framework's file and Foundry-backed checkpoint stores were considered and not used for that reason.
"""
import logging
import time
from collections.abc import Callable
from typing import Any

from agent_framework import FunctionInvocationContext, InMemoryCheckpointStorage, Workflow, WorkflowBuilder

from app.core import replies
from app.core.gateway_client import GatewayClient, GatewayReply
from app.core.identity import ActingIdentity
from app.core.maf_catalog_tools import TURN
from app.core.maf_write_steps import (
    AwaitConfirmation, Commit, Confirmation, Prepare, PrepareRequest, WriteContext,
)
from app.core.state import ConversationState, PausedWrite
from app.core.writes import CommitOutcome
from application.capabilities import catalog

log = logging.getLogger("tcc.orchestrator.writes")
NAME = "tcc-write"
Clock = Callable[[], float]


def build_write_flow(context: WriteContext, storage: InMemoryCheckpointStorage) -> Workflow:
    """A fresh graph: prepare, then the request step, then commit. The same graph on every run, so a checkpoint resumes on it."""
    prepare, wait, commit = Prepare(context), AwaitConfirmation(context), Commit(context)
    return (
        WorkflowBuilder(start_executor=prepare, checkpoint_storage=storage, name=NAME, output_from=[wait, commit])
        .add_edge(prepare, wait).add_edge(wait, commit).build()
    )


def _unavailable() -> GatewayReply:
    return GatewayReply(0, {"error": {"code": "write_flow_failed", "message": "the preview could not be held for confirmation", "retryable": True}})


async def prepare_body(ctx: FunctionInvocationContext, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> GatewayReply:
    """The body of every `*_prepare` tool: start the write workflow for the turn that is calling it."""
    return await prepare_write(ctx.kwargs[TURN], spec, args)


async def prepare_write(turn: Any, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> GatewayReply:
    """Start the write workflow for a prepare tool the model called; the gateway's reply to the preview.

    The paused workflow is left on `turn.flow` for the pipeline to keep for the reader's reply. A preview that
    was refused (not entitled, bad arguments) or carried no confirmation never pauses.
    """
    storage = InMemoryCheckpointStorage()
    context = WriteContext(turn.gateway, turn.who, turn.clock, turn.confirm_ttl_seconds, turn.forward)
    flow = build_write_flow(context, storage)
    try:
        result = await flow.run(PrepareRequest(spec.name, dict(args)))
    except Exception as exc:  # noqa: BLE001 - a framework fault must not look like a held preview
        log.error("the write workflow failed while preparing (%s)", type(exc).__name__)
        return _unavailable()
    reply, requests = context.prepared.reply, result.get_request_info_events()
    if reply is None:
        return _unavailable()
    if requests and flow.get_last_checkpoint_id():
        turn.flow = PausedWrite(storage, flow.get_last_checkpoint_id(), requests[0].request_id)
    return reply


def _resume_context(gateway: GatewayClient, who: ActingIdentity, clock: Clock) -> WriteContext:
    return WriteContext(gateway, who, clock)


async def _resume(held: PausedWrite, context: WriteContext, reply: Confirmation) -> CommitOutcome | None:
    """The outcome the workflow reached after `reply`, or None when it reached none."""
    result = await build_write_flow(context, held.storage).run(responses={held.request_id: reply}, checkpoint_id=held.checkpoint_id)
    outcomes = [o for o in result.get_outputs() if isinstance(o, CommitOutcome)]
    return outcomes[-1] if outcomes else None


async def commit_pending(
    gateway: GatewayClient, who: ActingIdentity, state: ConversationState, clock: Clock = time.monotonic,
) -> CommitOutcome:
    """The reader's `confirm`: resume the paused workflow, once. The pending change is cleared before anything is sent.

    Called from `TurnPipeline` after the exact-word gate, and nowhere else. A workflow that cannot be resumed
    says the outcome is unknown rather than that nothing happened: the commit may have been sent.
    """
    held, state.write = state.write, None
    if held is None:
        return CommitOutcome(replies.NOTHING_PENDING, False)
    try:
        outcome = await _resume(held, _resume_context(gateway, who, clock), Confirmation(True))
    except Exception as exc:  # noqa: BLE001 - after a possible send, "unknown" is the only honest answer
        log.error("the write workflow failed while committing (%s)", type(exc).__name__)
        outcome = None
    return outcome or CommitOutcome(replies.commit_failure("gateway_unreachable", ""), False, code="write_flow_failed")


async def cancel_pending(gateway: GatewayClient, who: ActingIdentity, state: ConversationState, clock: Clock = time.monotonic) -> bool:
    """The reader's `cancel`: refuse the request, so the workflow ends. True when something was waiting."""
    held, state.write = state.write, None
    if held is None:
        return False
    try:
        await _resume(held, _resume_context(gateway, who, clock), Confirmation(False))
    except Exception as exc:  # noqa: BLE001 - nothing was written by a preview, so a failed cancel changes nothing
        log.warning("the write workflow could not be cancelled cleanly (%s)", type(exc).__name__)
    return True


async def drop_pending(gateway: GatewayClient, who: ActingIdentity, state: ConversationState, clock: Clock = time.monotonic) -> bool:
    """Any other message: cancel the framework's pending request. True when a change was waiting and is now dropped."""
    held, state.write = state.write, None
    if held is None:
        return False
    try:
        await build_write_flow(_resume_context(gateway, who, clock), held.storage).cancel_pending_requests(
            [held.request_id], checkpoint_id=held.checkpoint_id,
        )
    except Exception as exc:  # noqa: BLE001 - nothing was written by a preview, so a failed drop changes nothing
        log.warning("the write workflow could not be dropped cleanly (%s)", type(exc).__name__)
    return True
