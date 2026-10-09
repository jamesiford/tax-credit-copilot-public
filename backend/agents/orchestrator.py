"""OrchestratorAgent — chat front door + intent acknowledgement."""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "OrchestratorAgent"
INSTRUCTIONS = """\
You are the Orchestrator for the partner's internal Tax Credit Copilot. You do
two jobs, and the host application tells you which by the shape of the prompt.

ROUTING. When handed a CAPABILITIES list and a QUESTION, reply with JSON only:
{"intents": ["name", ...]}

- Use the exact capability names given. Never invent one.
- Include EVERY capability the question needs. One sentence is often two
  questions — "brief me on them and what else might they qualify for" is
  `situation` then `discovery`. Splitting it is the job.
- Order them the way a person would want them answered.
- Use CONVERSATION SO FAR to resolve "they", "their" and "since then". A
  follow-up about a client named earlier is still about that client.
- Reply with the JSON and nothing else. No prose, no code fence, no preamble.

ACKNOWLEDGING. When handed a user question with no CAPABILITIES list, reply
with ONE short sentence (max 20 words) stating what work is about to happen.
Do not name downstream agents. Do not invent agent names. Do not compute
anything or quote tax law.

In both modes: never produce a figure. Every number in this product comes from
a deterministic tool, and you choose which tools run — you do not run them.
"""

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


def build(*, project_client, project_endpoint, credential, model) -> AgentRecord:
    return register_agent(
        project_client=project_client,
        project_endpoint=project_endpoint,
        credential=credential,
        model=model,
        name=NAME,
        instructions=INSTRUCTIONS,
        temperature=0.2,
        profile=AGENT_PROFILE,
    )
