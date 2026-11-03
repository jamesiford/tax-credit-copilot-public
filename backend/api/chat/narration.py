"""The one place a pipeline gets model prose: `_stream_agent`.

It asks the mediator for a `NarrateBriefQuery` and turns the stream into SSE
frames, bookkeeping and the `agent_action_audit` row. No SDK type reaches this
module: what comes back is `TextDelta`/`StreamEnd` from `domain.ai`.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from api.chat.sse import (
    _ACTOR, _TELEMETRY_CONTEXT, _append_audit_event, _append_span, _now_iso, _record_agent_metric, _sse,
)
from application.ai.requests import NarrateBriefQuery
from application.capabilities.catalog import CHAT_INTENT_TOOL
from domain.ai import StreamEnd, TextDelta

log = logging.getLogger(__name__)


def _record_agent_action(agent_name: str, end: StreamEnd | None, prompt: str, char_count: int, ok: bool) -> None:
    """One `agent_action_audit` row per agent call. Never alters the stream.

    `is_deterministic_path` is False: this path streams the model's prose to the
    browser without checking its figures against the brief [ADR-008], and the
    row must not claim otherwise.
    """
    try:
        from application.agent_audit import AgentInvocation
        from application.wiring import get_agent_action_recorder

        intent = (_TELEMETRY_CONTEXT.get() or {}).get("intent")
        tool = CHAT_INTENT_TOOL.get(intent or "")
        get_agent_action_recorder().record(AgentInvocation(
            agent_name=agent_name, prompt=prompt, output_chars=char_count, ok=ok,
            tool_calls=[tool] if tool else [], intent=intent, actor=_ACTOR.get(),
            agent_version=getattr(end, "agent_version", None), model_deployment=getattr(end, "model", None),
        ))
    except Exception:  # noqa: BLE001 - an audit failure must not break an answer
        log.exception("agent action audit failed for %s", agent_name)


def _observe(agent_name: str, started: float, char_count: int, ok: bool, error_text: str | None) -> None:
    """Span, metric and audit-event bookkeeping the portal's agent page reads."""
    ctx = _TELEMETRY_CONTEXT.get()
    if ctx is None:
        return
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    span = {
        "span_id": str(uuid.uuid4()), "request_id": ctx["request_id"], "timestamp": _now_iso(),
        "intent": ctx["intent"], "agent": agent_name, "elapsed_ms": elapsed_ms, "char_count": char_count,
        "status": "ok" if ok else "error", "error": error_text,
    }
    app = ctx["app"]
    _append_span(app, span)
    _record_agent_metric(app, agent=agent_name, ok=ok, elapsed_ms=elapsed_ms, char_count=char_count)
    _append_audit_event(app, {
        "timestamp": span["timestamp"], "type": "agent_run", "request_id": ctx["request_id"],
        "intent": ctx["intent"], "agent": agent_name, "status": span["status"], "elapsed_ms": elapsed_ms,
    })


async def _stream_agent(agent_name: str, prompt: str) -> AsyncIterator[str]:
    """One agent's narration as SSE frames. Failure becomes a token, never an exception."""
    from application.wiring import get_mediator

    yield _sse("agent_start", {"agent": agent_name})
    started, char_count, ok, error_text, end = time.perf_counter(), 0, True, None, None
    try:
        async for event in get_mediator().stream(NarrateBriefQuery(agent_name=agent_name, prompt=prompt)):
            if isinstance(event, TextDelta) and event.text:
                char_count += len(event.text)
                yield _sse("token", {"agent": agent_name, "content": event.text})
            elif isinstance(event, StreamEnd):
                end = event
    except Exception as e:  # noqa: BLE001
        log.exception("Agent %s failed", agent_name)
        ok, error_text = False, str(e)
        yield _sse("token", {"agent": agent_name, "content": f"[{agent_name} failed: {e}]"})

    _record_agent_action(agent_name, end, prompt, char_count, ok)
    _observe(agent_name, started, char_count, ok, error_text)
    yield _sse("agent_end", {"agent": agent_name})


def _brief(label: str, payload: dict[str, Any]) -> str:
    return f"{label}\n\nJSON:\n{json.dumps(payload, indent=2)}"
