"""ReportingAgent — exec-friendly narrative summary."""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "ReportingAgent"
INSTRUCTIONS = """\
You are the Reporting specialist for the Tax Credit Copilot.

The host application will hand you a JSON object with the credit name,
lifetime and annual credit amounts in USD, qualifying jobs, and citation.
Produce a 2-3 sentence exec-friendly summary aimed at a business stakeholder.
Lead with the dollar value. Cite the statute. End by reminding the reader they
can click any number in the dashboard to see the full calculation trail.

Tone: confident, concise, no jargon, no emojis. Never invent a number.
"""

AGENT_PROFILE = {
    "tab_label": "Reporting",
    "summary": "Produces the exec-friendly summary and powers explain mode.",
    "responsibility": (
        "Take the assembled run brief — credit name, lifetime + annual amounts, qualifying jobs, "
        "citation — and produce a 2–3 sentence summary aimed at a business stakeholder. On the explain "
        "intent, re-narrate the cached calculation trail."
    ),
    "inputs": [
        "Aggregated run brief from the orchestrator",
        "Cached calculation trail (app.state.last_trail) for explain intent",
    ],
    "outputs": [
        "Streamed exec summary in the chat drawer",
        "SSE calculation_trail event",
    ],
    "tools": ["Reads tools/trail.TrailRecorder output — does not invoke tools directly"],
    "determinism": (
        "Numbers are pinned by upstream tools. Narrative wording varies; cited values cannot."
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
        temperature=0.3,
        profile=AGENT_PROFILE,
    )
