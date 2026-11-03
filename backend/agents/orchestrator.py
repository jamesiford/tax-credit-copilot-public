"""OrchestratorAgent — chat front door + intent acknowledgement."""
from __future__ import annotations

from domain.ai import AgentSpec, ModelRole

from ._prompts import load_instructions


NAME = "OrchestratorAgent"
INSTRUCTIONS = load_instructions("orchestrator")

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


SPEC = AgentSpec(
    name=NAME, instructions=INSTRUCTIONS, role=ModelRole.ROUTER,
    temperature=0.2, profile=AGENT_PROFILE,
)
