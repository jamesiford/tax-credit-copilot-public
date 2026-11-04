"""ReportingAgent — exec-friendly narrative summary."""
from __future__ import annotations

from .roster import build_spec

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


SPEC = build_spec("reporting", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
