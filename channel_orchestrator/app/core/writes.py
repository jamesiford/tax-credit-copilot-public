"""The words that confirm a change and the one function that sends its commit. [CH-08, RM-10b]

A change is two steps, and the second is never the model's. A model may PREPARE (the write workflow,
`maf_write_flow`, asks for the preview and pauses on it); the change is made only when the SAME person, in the
SAME conversation, types one of a few exact words within the time limit. That reply resumes the workflow, whose
commit executor is the only caller of `send_commit`; `maf_write_flow.commit_pending` is called from
`TurnPipeline` and nowhere else, and no MAF tool, tool-spec or plan can name a commit: `tools.model_tools()`
excludes them and an attempt is refused and recorded.

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

import uuid
from dataclasses import dataclass
from typing import Any

from app.core import replies
from app.core.compose import compose_reply, provenance_footer
from app.core.gateway_client import GatewayClient
from app.core.identity import ActingIdentity
from app.core.state import PendingWrite
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
    """What the owner is told, and whether the change was recorded. `runs` are the results shown (the commit, and a package link)."""

    text: str
    made: bool
    tool: str = ""
    code: str = "ok"
    runs: tuple[ToolRun, ...] = ()


def commit_tool_for(prepare_tool: str) -> str:
    """The commit that pairs with a prepare; only a `_prepare` has one."""
    if not prepare_tool.endswith("_prepare"):
        raise ValueError(f"{prepare_tool} is not a preview")
    return prepare_tool[: -len("_prepare")] + "_commit"


async def _package_link(gateway: GatewayClient, who: ActingIdentity, args: dict[str, Any]) -> tuple[ToolRun | None, str]:
    """After a claim package is built, its link from the gateway (never a storage URL), or why not."""
    wanted = {k: args[k] for k in ("client_id", "tax_year") if k in args}
    reply = await gateway.call_tool(who, "claim_package_link", wanted)
    if reply.ok:
        return ToolRun("claim_package_link", wanted, reply.body, "claim_package_link"), ""
    return None, f"The package was built, but I could not get its link: {reply.error_message or reply.error_code}."


async def send_commit(gateway: GatewayClient, who: ActingIdentity, pending: PendingWrite) -> CommitOutcome:
    """Send the confirmed change's commit for `who`, once, and say what happened.

    Called by the write workflow's commit executor and by nothing else. It sends a fresh idempotency key and
    the token the preview issued; the gateway and the API check the person, the tool, the arguments, the
    expiry and that the token is unused, and refuse otherwise.
    """
    tool = commit_tool_for(pending.tool)
    reply = await gateway.call_tool(
        who, tool, pending.args, idempotency_key=uuid.uuid4().hex, confirmation_token=pending.token,
    )
    if not reply.ok:
        return CommitOutcome(replies.commit_failure(reply.error_code, reply.error_message), False, tool, reply.error_code)
    runs, note = [ToolRun(tool, pending.args, reply.body, tool)], ""
    if tool == "claim_package_create_commit":
        link, note = await _package_link(gateway, who, pending.args)
        runs += [link] if link else []
    composed = compose_reply("", runs, None)
    text = "\n\n".join(p for p in (composed.text, provenance_footer(runs), note) if p)
    return CommitOutcome(text, True, tool, runs=tuple(runs))
