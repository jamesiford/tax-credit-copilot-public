"""The confirmation protocol for changes: the ONLY code that can send a commit. [CH-08]

A change is two steps, and the second is never the model's. A model may PREPARE (the tool
runner holds the token and the preview is shown); the change is made only when the SAME
person, in the SAME conversation, types one of a few exact words within the time limit.
`commit_pending` is called from `TurnPipeline` and nowhere else, and no MAF tool, tool-spec
or plan can name a commit: `tools.model_tools()` excludes them and an attempt is refused and
recorded.

Rules, each tested:

- exact words only: `confirm`, `yes, apply`, `cancel` (case and trailing punctuation
  ignored); "please go ahead" is a new question, not a confirmation;
- the state is keyed by person AND conversation, so somebody else's `confirm` finds
  nothing;
- any other message drops the pending change, so a stale preview cannot be confirmed
  later by a stray `confirm`;
- the pending change is cleared BEFORE the commit is sent and a commit is never retried by
  the orchestrator: a commit whose answer was lost is reported as unknown, and the person
  checks the record. The gateway's idempotency key makes a deliberate re-ask safe.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from app.core import replies
from app.core.compose import compose_reply, provenance_footer
from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.state import ConversationState, PendingWrite
from app.core.tools import ToolRun

_TRAILING = ".!"


def parse_command(text: str) -> str | None:
    """`confirm`, `cancel` or None. Exact words only."""
    said = (text or "").strip().lower().rstrip(_TRAILING).strip()
    if said in replies.CONFIRM_WORDS:
        return "confirm"
    return "cancel" if said in replies.CANCEL_WORDS else None


@dataclass(frozen=True)
class CommitOutcome:
    """What the owner is told, and whether the change was recorded."""

    text: str
    made: bool
    tool: str = ""
    code: str = "ok"


def commit_tool_for(prepare_tool: str) -> str:
    """The commit that pairs with a prepare; only a `_prepare` has one."""
    if not prepare_tool.endswith("_prepare"):
        raise ValueError(f"{prepare_tool} is not a preview")
    return prepare_tool[: -len("_prepare")] + "_commit"


async def commit_pending(
    gateway: GatewayClient, who: ActingIdentity, state: ConversationState,
    clock: Callable[[], float] = time.monotonic,
) -> CommitOutcome:
    """Send the held commit for `who`, once. Clears the pending change first."""
    pending: PendingWrite | None = state.pending
    state.pending = None
    if pending is None:
        return CommitOutcome(replies.NOTHING_PENDING, False)
    if clock() >= pending.expires_at:
        return CommitOutcome(replies.EXPIRED, False, pending.tool, "expired")
    tool = commit_tool_for(pending.tool)
    reply = await gateway.call_tool(
        who, tool, pending.args, idempotency_key=uuid.uuid4().hex, confirmation_token=pending.token,
    )
    if not reply.ok:
        return CommitOutcome(replies.commit_failure(reply.error_code, reply.error_message), False, tool, reply.error_code)
    run = ToolRun(tool, pending.args, reply.body, tool)
    composed = compose_reply("", [run], None)
    text = "\n\n".join(p for p in (composed.text, provenance_footer([run])) if p)
    return CommitOutcome(text, True, tool)
