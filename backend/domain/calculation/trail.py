"""Per-request calculation trail capture.

Tools record their {step, inputs, formula, output, citation} dicts into the
active `TrailRecorder` for the current request. The chat endpoint reads them
out after the agent run finishes and forwards them to the UI as SSE events.

Implemented with `contextvars` so concurrent requests don't cross-contaminate.
"""
from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrailStep:
    step: str
    inputs: dict[str, Any]
    formula: str
    output: dict[str, Any]
    citation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "inputs": self.inputs,
            "formula": self.formula,
            "output": self.output,
            "citation": self.citation,
        }


@dataclass
class TrailRecorder:
    title: str = ""
    citation: str = ""
    steps: list[TrailStep] = field(default_factory=list)

    def record(self, *, step: str, inputs: dict[str, Any], formula: str, output: dict[str, Any], citation: str) -> None:
        self.steps.append(TrailStep(step=step, inputs=inputs, formula=formula, output=output, citation=citation))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "citation": self.citation,
            "steps": [s.to_dict() for s in self.steps],
        }
        # SHA-256 over the canonical trail bytes — self-fingerprinting for audit.
        canonical = json.dumps(d, sort_keys=True, separators=(',', ':')).encode()
        d["evidence_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
        return d


_RECORDER: ContextVar[TrailRecorder | None] = ContextVar("calc_trail_recorder", default=None)


def current_recorder() -> TrailRecorder | None:
    return _RECORDER.get()


def set_recorder(recorder: TrailRecorder) -> Token:
    return _RECORDER.set(recorder)


def reset_recorder(token: Token) -> None:
    _RECORDER.reset(token)
