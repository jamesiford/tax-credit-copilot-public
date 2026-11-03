"""SSE framing and the in-process span bookkeeping the portal's agent page reads.

`_TELEMETRY_CONTEXT` carries the request's app and intent to `narration._stream_agent`;
`_ACTOR` carries who asked, for `tcc_ops.agent_action_audit`. Both are ContextVars so
a pipeline never has to thread them through its arguments.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime
from typing import Any

_TELEMETRY_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("chat_telemetry_context", default=None)
#: Who asked, for `tcc_ops.agent_action_audit`. Set once per request by `chat()`.
_ACTOR: ContextVar[str | None] = ContextVar("chat_actor", default=None)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _append_audit_event(app, event: dict[str, Any]) -> None:
    if not hasattr(app.state, "audit_events"):
        app.state.audit_events = []
    app.state.audit_events.append(event)
    if len(app.state.audit_events) > 2000:
        app.state.audit_events = app.state.audit_events[-2000:]


def _record_agent_metric(app, *, agent: str, ok: bool, elapsed_ms: int, char_count: int) -> None:
    if not hasattr(app.state, "agent_metrics"):
        app.state.agent_metrics = {}
    cur = app.state.agent_metrics.get(agent, {
        "runs": 0,
        "failures": 0,
        "total_ms": 0,
        "avg_ms": 0,
        "last_run_at": None,
        "last_status": "unknown",
        "chars_streamed": 0,
    })
    cur["runs"] += 1
    if not ok:
        cur["failures"] += 1
    cur["total_ms"] += elapsed_ms
    cur["avg_ms"] = round(cur["total_ms"] / max(1, cur["runs"]))
    cur["last_run_at"] = _now_iso()
    cur["last_status"] = "ok" if ok else "error"
    cur["chars_streamed"] += char_count
    app.state.agent_metrics[agent] = cur


def _append_span(app, span: dict[str, Any]) -> None:
    if not hasattr(app.state, "agent_spans"):
        app.state.agent_spans = []
    app.state.agent_spans.append(span)
    if len(app.state.agent_spans) > 3000:
        app.state.agent_spans = app.state.agent_spans[-3000:]
