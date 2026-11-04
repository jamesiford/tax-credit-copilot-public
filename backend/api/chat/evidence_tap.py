"""Collect the capabilities a pipeline ran and stream their evidence. [CH-15d]

The pipelines call a capability, take its `.facts` for the narrator and drop the
envelope. Changing each of them to hand the envelope back would rewrite nine
functions that are already near their size limits; instead a pipeline passes the
result through `tap`, which notes it and returns it unchanged, and `with_evidence`
wraps the pipeline's frames and emits one `evidence` event per capability that ran.

The event goes out BEFORE the next frame the pipeline yields, so the evidence for
a capability arrives ahead of the narration of it and always before `done`. The
sink is per request (a ContextVar, so two readers never share one) and is cleared
with `set(None)`, not `reset(token)`: an async generator can be closed from a
different context than it was opened in, and `reset` would raise there.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import AsyncIterator

from api.chat.evidence import evidence_item
from api.chat.sse import _AUTHENTICATED, _sse
from application.capabilities.envelope import ToolResult

_SINK: ContextVar[list[ToolResult] | None] = ContextVar("chat_evidence_sink", default=None)


def tap(result: ToolResult) -> ToolResult:
    """Note a capability's result for the evidence stream and hand it back untouched."""
    sink = _SINK.get()
    if sink is not None:
        sink.append(result)
    return result


def _drain(intent: str, sink: list[ToolResult], first_ordinal: int) -> list[str]:
    """Evidence frames for what ran since the last drain; a result with nothing to show emits none."""
    frames = []
    for offset, result in enumerate(sink, start=first_ordinal):
        item = evidence_item(intent, result, offset, authenticated=_AUTHENTICATED.get())
        if item is not None:
            frames.append(_sse("evidence", item))
    sink.clear()
    return frames


async def with_evidence(intent: str, frames: AsyncIterator[str]) -> AsyncIterator[str]:
    """`frames`, with an `evidence` event ahead of the first frame after each capability ran."""
    sink: list[ToolResult] = []
    _SINK.set(sink)
    sent = 0
    try:
        async for frame in frames:
            if sink:
                pending = len(sink)
                for out in _drain(intent, sink, sent + 1):
                    yield out
                sent += pending
            yield frame
        if sink:
            for out in _drain(intent, sink, sent + 1):
                yield out
    finally:
        _SINK.set(None)
