"""The one place a pipeline gets model prose: `_stream_agent`.

It asks the mediator for a `NarrateBriefQuery` and turns the stream into SSE
frames, bookkeeping and the `agent_action_audit` row. No SDK type reaches this
module: what comes back is `TextDelta`/`StreamEnd` from `domain.ai`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from api.chat.sse import (
    _ACTOR, _TELEMETRY_CONTEXT, _append_audit_event, _append_span, _now_iso, _record_agent_metric, _sse,
)
from application.ai.requests import NarrateBriefQuery
from application.audit_alert import audit_write_failed
from application.capabilities.catalog import CHAT_INTENT_TOOL
from domain.ai import OutputWithheld, SafetyRefusal, StreamEnd, TextDelta

log = logging.getLogger(__name__)


def _record_agent_action(agent_name: str, end: StreamEnd | None, prompt: str, char_count: int, ok: bool) -> None:
    """One `agent_action_audit` row per agent call. Never alters the stream.

    `is_deterministic_path` is False: this path streams the model's prose to the
    browser without checking its figures against the brief [ADR-008], and the
    row must not claim otherwise.
    """
    try:
        from application.agent_audit import AgentInvocation
        from application.services import get_agent_action_recorder

        intent = (_TELEMETRY_CONTEXT.get() or {}).get("intent")
        tool = CHAT_INTENT_TOOL.get(intent or "")
        get_agent_action_recorder().record(AgentInvocation(
            agent_name=agent_name, prompt=prompt, output_chars=char_count, ok=ok,
            tool_calls=[tool] if tool else [], intent=intent, actor=_ACTOR.get(),
            agent_version=getattr(end, "agent_version", None), model_deployment=getattr(end, "model", None),
        ))
    except Exception as exc:  # noqa: BLE001 - an audit failure must not break an answer, and must not be silent
        log.exception("agent action audit failed for %s", agent_name)
        audit_write_failed("agent_audit", "portal_chat_record", exc, fatal=False)


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


def _degraded_token(prompt: str, char_count: int, failure: Exception) -> str | None:
    """The engine's figures in place of prose, or None when there is nothing to show.

    A safety refusal says why in its own words. Otherwise the explanatory sentence is
    said once per request: a pipeline that narrates five times against a dead model
    should not apologise five times.
    """
    from api.chat.degraded import INTERRUPTED_SENTENCE, UNAVAILABLE_SENTENCE, degraded_message

    ctx = _TELEMETRY_CONTEXT.get()
    said = bool(ctx and ctx.get("degraded_said"))
    refusal = isinstance(failure, SafetyRefusal)
    sentence = failure.reader_sentence if refusal else (INTERRUPTED_SENTENCE if char_count else UNAVAILABLE_SENTENCE)
    text = degraded_message(
        prompt, sentence=sentence, with_sentence=refusal or char_count > 0 or not said, after_text=char_count > 0,
    )
    if ctx is not None:
        ctx["degraded_said"] = True
    return text or None


class _Run:
    """What one narration has shown so far; read by the bookkeeping after the stream ends."""

    def __init__(self) -> None:
        self.chars, self.end = 0, None


def _output_gate():
    """A gate that holds back prose breaking an output rule, or None when the policy is off."""
    from application.ai.safety.stream_gate import OutputGate
    from application.services import get_output_policy

    policy = get_output_policy()
    return OutputGate(policy) if policy is not None else None


def _withheld(gate) -> None:
    from application.services import get_ai_telemetry

    get_ai_telemetry().count("ai.output_withheld")
    log.warning("model prose withheld by output policy: %s", ",".join(gate.blocked))
    raise OutputWithheld(gate.blocked)


class _Release:
    """The output gate, or a pass-through when the policy is switched off."""

    def __init__(self) -> None:
        self._gate = _output_gate()

    def _checked(self, released: str) -> str:
        if self._gate is not None and self._gate.blocked:
            _withheld(self._gate)
        return released

    def feed(self, text: str) -> str:
        """The part of `text` that may be shown now; raises `OutputWithheld` once a rule fires."""
        return text if self._gate is None else self._checked(self._gate.feed(text))

    def finish(self) -> str:
        """Whatever is still held, if it passes."""
        return "" if self._gate is None else self._checked(self._gate.finish())


async def _frames(agent_name: str, prompt: str, run: _Run) -> AsyncIterator[str]:
    """Token frames for one narration, each released only once the output policy accepts it."""
    from application.services import get_mediator

    release = _Release()
    async for event in get_mediator().stream(NarrateBriefQuery(agent_name=agent_name, prompt=prompt)):
        if isinstance(event, StreamEnd):
            run.end = event
        elif isinstance(event, TextDelta) and event.text:
            if text := release.feed(event.text):
                run.chars += len(text)
                yield _sse("token", {"agent": agent_name, "content": text})
    if tail := release.finish():
        run.chars += len(tail)
        yield _sse("token", {"agent": agent_name, "content": tail})


async def _stream_agent(agent_name: str, prompt: str, *, degrade: bool = True) -> AsyncIterator[str]:
    """One agent's narration as SSE frames. Failure becomes a token, never an exception.

    With `degrade` (the default) a model that cannot narrate yields the engine's own
    figures instead of an error. A caller with its own fallback — the page summary —
    passes False and keeps the `[Agent failed: …]` marker it looks for.
    """
    yield _sse("agent_start", {"agent": agent_name})
    started, ok, error_text, run = time.perf_counter(), True, None, _Run()
    try:
        async for frame in _frames(agent_name, prompt, run):
            yield frame
    except asyncio.CancelledError:
        # The reader went away. Record what was written, then let the cancellation through.
        _record_agent_action(agent_name, run.end, prompt, run.chars, False)
        _observe(agent_name, started, run.chars, False, "cancelled by the client")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("Agent %s failed", agent_name)
        ok, error_text = False, str(e)
        shown = _degraded_token(prompt, run.chars, e) if degrade else None
        yield _sse("token", {"agent": agent_name, "content": shown or f"[{agent_name} failed: {e}]"})

    _record_agent_action(agent_name, run.end, prompt, run.chars, ok)
    _observe(agent_name, started, run.chars, ok, error_text)
    yield _sse("agent_end", {"agent": agent_name})


def _brief(label: str, payload: dict[str, Any]) -> str:
    return f"{label}\n\nJSON:\n{json.dumps(payload, indent=2)}"


def _question(message: str) -> str:
    """What the reader typed, fenced as data. It goes to a model; it is not an instruction to it."""
    from application.ai.safety.untrusted import UntrustedText

    return UntrustedText(message, "reader question").fenced()
