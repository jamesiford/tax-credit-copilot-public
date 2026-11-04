"""What the hosting shell does with a request, without the hosting framework. [CH-08]

`main.py` registers one Responses handler; everything that handler decides lives here so it can be
tested with plain objects. It reads the identity signals the platform sent, resolves the acting
person, answers the debug `/whoami` when (and only when) `CHANNEL_DEBUG_WHOAMI` is on, and otherwise
hands the message to the turn pipeline.

`context` is the Responses `ResponseContext`: this module uses only `client_headers`,
`platform_context`, `conversation_id`, `conversation_chain_id` and `response_id`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any

from app.core.identity import ActingIdentity, Refusal, describe_signals, resolve_identity
from app.core.modelprobe import run_modelprobe
from app.core.netcheck import run_netcheck
from app.wiring import Orchestrator

log = logging.getLogger("tcc.orchestrator.host")
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


def signals_of(context: Any) -> dict[str, str]:
    """The identity signals the platform sent, lower-cased, with the original subject flattened."""
    signals = {str(k).lower(): str(v) for k, v in (context.client_headers or {}).items()}
    platform = context.platform_context
    subject = getattr(platform, "original_subject", None)
    for suffix in ("oid", "tid", "idtype"):
        value = getattr(subject, suffix, None) if subject else None
        if value:
            signals[f"x-ms-original-subject-{suffix}"] = value
    if getattr(platform, "user_id_key", None):
        signals["x-agent-user-id"] = platform.user_id_key
    return signals


def conversation_of(context: Any) -> str | None:
    """A stable conversation key: the explicit conversation, else the response chain."""
    return context.conversation_id or getattr(context, "conversation_chain_id", None)


def who_is_asking(orchestrator: Orchestrator, context: Any) -> ActingIdentity | Refusal:
    """The acting person for this request, or why not."""
    correlation = _SAFE_ID.sub("", str(getattr(context, "response_id", "") or ""))[:64] or uuid.uuid4().hex
    settings = orchestrator.settings
    return resolve_identity(
        signals_of(context), sources=settings.identity_sources, tenant_id=settings.tenant_id,
        channel=settings.channel, conversation_id=conversation_of(context), correlation_id=correlation,
    )


def whoami(orchestrator: Orchestrator, context: Any, identity: ActingIdentity | Refusal) -> str:
    """The identity spike's report: signals received and what was resolved. Never a credential."""
    settings = orchestrator.settings
    resolved = (
        {"resolved": True, "source": identity.source, "oid": identity.oid, "tenant": identity.tenant_id,
         "display_name": identity.name, "channel": identity.channel, "conversation": identity.conversation_id}
        if isinstance(identity, ActingIdentity) else {"resolved": False, "reason": identity.reason}
    )
    return json.dumps({
        "agent": {"name": settings.agent_name, "version": settings.agent_version, "channel": settings.channel},
        "identity": resolved, "signals": describe_signals(signals_of(context)),
        "sources": list(settings.identity_sources), "conversation": conversation_of(context),
        "providers": list(settings.ai.provider_chain), "tools_available": orchestrator.chain.tools_available,
        "model_configured": orchestrator.chain.configured, "turns": orchestrator.pipeline.status(),
    }, indent=2)


async def diagnostics(orchestrator: Orchestrator, command: str) -> str:
    """`/netcheck` (where can this container connect) or `/modelprobe` (the sample's model call). Debug only."""
    env = os.environ
    if command == "/modelprobe":
        return await run_modelprobe(env)
    settings = orchestrator.settings
    return await asyncio.get_running_loop().run_in_executor(None, lambda: run_netcheck(
        env=env, project_endpoint=settings.ai.foundry_endpoint or "", gateway_url=settings.gateway_url,
        providers=tuple(settings.ai.provider_chain)))


async def answer(orchestrator: Orchestrator, context: Any, text: str) -> str:
    """The reply text for one request."""
    identity = who_is_asking(orchestrator, context)
    command = text.strip().lower() if orchestrator.settings.debug_whoami else ""
    if command == "/whoami":
        return whoami(orchestrator, context, identity)
    if command in ("/netcheck", "/modelprobe"):
        return await diagnostics(orchestrator, command)
    if isinstance(identity, Refusal):
        log.warning("turn refused: %s", identity.reason)
    reply = await orchestrator.pipeline.handle(text, identity if isinstance(identity, ActingIdentity) else None)
    if isinstance(identity, Refusal) and orchestrator.settings.debug_whoami:
        return f"{reply.text}\n\n```\n{whoami(orchestrator, context, identity)}\n```"
    return reply.text
