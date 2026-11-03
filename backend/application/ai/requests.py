"""The mediator requests model access goes through. [AI-02]

All three are `StreamingQuery`s: asking a model is a read — it changes nothing the
business believes — whose answer arrives as a stream. Making them requests, not
function calls, is what puts timing, logging and (later) policy on every model
call without any pipeline remembering to.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.mediator import StreamingQuery


@dataclass(frozen=True)
class NarrateBriefQuery(StreamingQuery):
    """Have one named agent narrate a deterministic brief.

    `prompt` is the brief the engine produced, already assembled by the caller;
    the agent may add words around its figures, never a figure of its own.
    """

    agent_name: str = ""
    prompt: str = ""

    def validate(self) -> None:
        if not self.agent_name or not self.prompt:
            raise ValueError("a narration needs an agent name and a prompt")


@dataclass(frozen=True)
class RouteQuestionQuery(StreamingQuery):
    """Ask the router which capabilities a question needs. Returns JSON text.

    The model chooses WHICH deterministic tool runs; it never produces a figure.
    """

    prompt: str = ""

    def validate(self) -> None:
        if not self.prompt:
            raise ValueError("a routing request needs a prompt")


@dataclass(frozen=True)
class ChannelNarrationQuery(StreamingQuery):
    """Narrate a channel answer with the channel narrator (Prompt 4's entry point).

    The narrator writes only `{{facts.…}}` placeholders; the composer substitutes
    the engine's figures and the numeric guard checks the result [ADR-008].
    """

    prompt: str = ""

    def validate(self) -> None:
        if not self.prompt:
            raise ValueError("a channel narration needs a prompt")
