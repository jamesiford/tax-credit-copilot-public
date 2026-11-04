"""What planning produced, and the one place its reply is composed. [CH-08, RM-10a]

Every planner (the agent, the two degraded ones, the review-pack workflow) hands the turn a `Planned`. The reply
is composed from the turn's tool results here and nowhere else: the agent's output middleware, the degraded
planners' narration and the workflow's last step all call `composed_for`, so there is one path from a model's
words (or none) to the reader, and it is the verbatim composer and the numeric guard.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.compose import compose_reply
from app.core.maf_chat import ModelTrace
from app.core.tools import ToolRunner
from application.composer import Composed
from application.knowledge import Passage


@dataclass
class Planned:
    """What planning produced. `composed` is set once the reply has been composed (by the agent's output middleware or on demand)."""

    mode: str
    narration: str | None = None
    composed: Composed | None = None
    model_used: bool = False
    degraded: bool = False
    hosts: tuple[str, ...] = ()
    reference: tuple[Passage, ...] = ()
    trace: ModelTrace = field(default_factory=ModelTrace)

    def narrate(self, raw: str | None) -> None:
        """Take a narration; whatever was composed before it no longer describes it."""
        self.narration, self.composed = raw, None

    def composed_for(self, runner: ToolRunner) -> Composed:
        """The composed reply for the turn's results and this narration (the platform's blocks alone when there is none)."""
        if self.composed is None:
            self.composed = compose_reply(runner.question, runner.runs, self.narration, self.hosts)
        return self.composed

    def fall_back(self) -> None:
        """The model layer failed: forget what it said and mark the answer as the platform's own."""
        self.degraded, self.narration, self.composed, self.reference = True, None, None, ()
