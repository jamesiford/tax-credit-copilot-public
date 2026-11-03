"""Handlers for the model-access requests. [AI-02]

Each is a few lines on purpose: resolve the service, name the agent, stream. They
depend only on the narration service (and through it, ports), so none can import
an SDK, and the cross-cutting concerns live in the service, not in three copies.
"""
from application.ai.handlers.channel import handle_channel_narration
from application.ai.handlers.narrate import handle_narrate_brief
from application.ai.handlers.route import ROUTER_AGENT, handle_route_question

__all__ = ["ROUTER_AGENT", "handle_channel_narration", "handle_narrate_brief", "handle_route_question"]
