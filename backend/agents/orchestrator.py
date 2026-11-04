"""OrchestratorAgent — chat front door + intent acknowledgement."""
from __future__ import annotations

from .roster import build_spec

AGENT_PROFILE = {
    "tab_label": "Orchestrator",
    "summary": "Acknowledges the question and tees up the run.",
    "responsibility": (
        "Produce one short sentence acknowledging the user request and naming the upcoming "
        "work — never names downstream agents, never quotes numbers."
    ),
    "inputs": [
        "Raw user message from the chat drawer",
        "Detected intent (eligibility · portfolio · discovery · explain · simulate)",
        "Detected jurisdiction (when present)",
    ],
    "outputs": [
        "One-sentence acknowledgement streamed back to the UI as the first chat token",
    ],
    "tools": ["No Python tools. Acknowledgement-only prompt agent."],
    "determinism": (
        "LLM-narrated, single short sentence. Cannot compute or quote tax law — has no tools attached."
    ),
}


SPEC = build_spec("orchestrator", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
