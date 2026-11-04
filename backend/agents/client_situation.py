"""ClientSituationAgent — why you would call this client, in their own numbers.

Deliberately NOT ReportingAgent. That one is told to "lead with the dollar
value", which is the exact instinct this screen exists to correct: a client one
hire from a threshold is worth $0 today, the same $0 as one fifty hires short,
so leading with value buries the client worth calling. An agent arguing against
the ranking it is sitting on would be worse than no agent.
"""
from __future__ import annotations

from .roster import build_spec

AGENT_PROFILE = {
    "tab_label": "Client Situation",
    "summary": "Explains why a client is worth calling, in the order the ranking put them.",
    "responsibility": (
        "Read the JSON brief built by application/queries/get_client_situation.py and state "
        "the leading priority band, the programme-year it applies to, and the one number "
        "that matters for that band."
    ),
    "inputs": [
        "JSON brief: by_band, lead_band, programs[], tax_years[], identified_usd, "
        "opportunity_usd, exposure_usd, claimed_is_unverified, assessed",
    ],
    "outputs": [
        "Streamed 3-5 sentence situation summary in the chat drawer",
    ],
    "tools": [
        "domain/coverage.py · situation() — pure ranking over recorded claims, no payroll",
    ],
    "determinism": (
        "The brief is deterministic: it reads recorded coverage and orders it by "
        "PriorityBand. Narrative wording varies; every figure is pinned by the brief."
    ),
}


SPEC = build_spec("client_situation", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
