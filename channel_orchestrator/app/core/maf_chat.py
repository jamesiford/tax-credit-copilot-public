"""What the chat clients in the MAF layer share: the turn's trace, the message shape, the loop's limits. [CH-08, RM-09]

Two clients serve the agent (`PortChatClient` over `ModelChain`, and the framework's own OpenAI client for a
foundry-only chain). Both feed the same audit report, so the trace of what the model layer did lives here, once.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.models import ModelTurn
from domain.ai import ChatMessage, ToolCall


@dataclass
class ModelTrace:
    """What the model layer did this turn, for the audit report: the turns taken and the prompt sent each time."""

    turns: list[ModelTurn] = field(default_factory=list)
    prompt_parts: list[str] = field(default_factory=list)

    @property
    def last(self) -> ModelTurn | None:
        """The most recent model turn, or None when no model was called: the audit reports the model that answered last."""
        return self.turns[-1] if self.turns else None

    def sent(self, messages: Any) -> None:
        """Note what is about to be sent to a model (the audit hashes it), whether or not the model answers."""
        self.prompt_parts.append("\n".join(m.content for m in messages))

    def took(self, turn: ModelTurn) -> None:
        """Note a turn a model took."""
        self.turns.append(turn)


def loop_limits(max_calls: int) -> dict[str, Any]:
    """The framework's tool-loop limits for a turn budget of `max_calls`: a backstop, since the budget middleware refuses first.

    Tools run one at a time, because their order is the order of the answer.
    """
    return {"max_iterations": max_calls + 2, "max_function_calls": max_calls + 1, "allow_concurrent_invocation": False}


def as_chat_messages(messages: Any, instructions: str | None) -> list[ChatMessage]:
    """MAF's messages as the model adapters' `ChatMessage`s (the egress check and the prompt hash read this shape)."""
    out = [ChatMessage("system", instructions)] if instructions else []
    for message in messages:
        calls = tuple(
            ToolCall(c.call_id, c.name, c.arguments if isinstance(c.arguments, str) else json.dumps(c.arguments or {}))
            for c in message.contents if c.type == "function_call"
        )
        results = [c for c in message.contents if c.type == "function_result"]
        if results:
            out += [ChatMessage("tool", str(r.result), tool_call_id=r.call_id) for r in results]
        elif calls:
            out.append(ChatMessage("assistant", message.text or "", tool_calls=calls))
        else:
            out.append(ChatMessage(str(message.role), message.text or ""))
    return out
