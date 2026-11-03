"""Foundry hosted-agent entry point: the Responses protocol on port 8088. [CH-08]

The platform bridges Teams and Microsoft 365 Copilot to this container's Responses endpoint
(published agents use the Activity protocol on the Bot Service side and the platform converts), so
this file implements the Responses protocol only. The host provides `/readiness` and a graceful
shutdown on SIGTERM. Everything else is `app.core`; this shell resolves identity from what the
platform sent, hands the message to the turn pipeline and returns its text. No streaming and no
cards: a published agent cannot stream, and the answer is composed whole.

    python -m app.main
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

from azure.ai.agentserver.responses import ResponseContext, ResponsesAgentServerHost, TextResponse

from app.core.identity import ActingIdentity, Refusal, describe_signals, resolve_identity
from app.wiring import Orchestrator, build_orchestrator

log = logging.getLogger("tcc.orchestrator")
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


def signals_of(context: ResponseContext) -> dict[str, str]:
    """The identity signals the platform sent, lower-cased, with the original subject flattened."""
    signals = {k.lower(): v for k, v in (context.client_headers or {}).items()}
    platform = context.platform_context
    subject = getattr(platform, "original_subject", None)
    for suffix in ("oid", "tid", "idtype"):
        value = getattr(subject, suffix, None) if subject else None
        if value:
            signals[f"x-ms-original-subject-{suffix}"] = value
    if platform.user_id_key:
        signals["x-agent-user-id"] = platform.user_id_key
    return signals


def conversation_of(context: ResponseContext) -> str | None:
    """A stable conversation key: the explicit conversation, else the response chain."""
    return context.conversation_id or context.conversation_chain_id


def who_is_asking(app: Orchestrator, context: ResponseContext) -> ActingIdentity | Refusal:
    """The acting person for this request, or why not."""
    correlation = _SAFE_ID.sub("", context.response_id or "")[:64] or uuid.uuid4().hex
    return resolve_identity(
        signals_of(context), sources=app.settings.identity_sources, tenant_id=app.settings.tenant_id,
        channel=app.settings.channel, conversation_id=conversation_of(context), correlation_id=correlation,
    )


def whoami(app: Orchestrator, context: ResponseContext, identity: ActingIdentity | Refusal) -> str:
    """The identity spike's report. Debug only: names the signals received and what was resolved, never a credential."""
    resolved = (
        {"resolved": True, "source": identity.source, "oid": identity.oid, "tenant": identity.tenant_id}
        if isinstance(identity, ActingIdentity) else {"resolved": False, "reason": identity.reason}
    )
    return json.dumps({
        "agent": {"name": app.settings.agent_name, "version": app.settings.agent_version, "channel": app.settings.channel},
        "identity": resolved, "signals": describe_signals(signals_of(context)),
        "sources": list(app.settings.identity_sources), "conversation": conversation_of(context),
        "providers": list(app.settings.ai.provider_chain),
        "tools_available": app.chain.tools_available, "model_configured": app.chain.configured,
        "turns": app.pipeline.status(),
    }, indent=2)


def create_host(app: Orchestrator | None = None) -> ResponsesAgentServerHost:
    """The Responses host with this orchestrator's handler registered."""
    orchestrator = app or build_orchestrator()
    host = ResponsesAgentServerHost()

    @host.response_handler
    async def handle(request: Any, context: ResponseContext, cancellation_signal: Any) -> TextResponse:
        text = await context.get_input_text()
        identity = who_is_asking(orchestrator, context)
        if orchestrator.settings.debug_whoami and text.strip().lower() == "/whoami":
            return TextResponse(context, request, text=whoami(orchestrator, context, identity))
        who = identity if isinstance(identity, ActingIdentity) else None
        if who is None:
            log.warning("turn refused: %s", identity.reason)
        reply = await orchestrator.pipeline.handle(text, who)
        return TextResponse(context, request, text=reply.text)

    return host


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    create_host().run()


if __name__ == "__main__":
    main()
