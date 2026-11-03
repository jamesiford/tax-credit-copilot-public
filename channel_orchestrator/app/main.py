"""Foundry hosted-agent entry point: the Responses protocol on port 8088. [CH-08]

The platform bridges Teams and Microsoft 365 Copilot to this container's Responses endpoint
(published agents use the Activity protocol on the Bot Service side and the platform converts), so
this file implements the Responses protocol only. The host provides `/readiness` and a graceful
shutdown on SIGTERM. Everything else is `app.host` and `app.core`; this shell registers one handler
and returns its text. No streaming and no cards: a published agent cannot stream, and the answer is
composed whole.

    python -m app.main

This is the only module that imports the hosting package, so everything else runs (and is tested)
without it.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from azure.ai.agentserver.responses import ResponseContext, ResponsesAgentServerHost, TextResponse

from app.host import answer
from app.wiring import Orchestrator, build_orchestrator


def create_host(orchestrator: Orchestrator | None = None) -> ResponsesAgentServerHost:
    """The Responses host with this orchestrator's handler registered."""
    built = orchestrator or build_orchestrator()
    host = ResponsesAgentServerHost()

    @host.response_handler
    async def handle(request: Any, context: ResponseContext, cancellation_signal: Any) -> TextResponse:
        text = await answer(built, context, await context.get_input_text())
        return TextResponse(context, request, text=text)

    return host


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    create_host().run()


if __name__ == "__main__":
    main()
