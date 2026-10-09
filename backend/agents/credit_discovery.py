"""CreditDiscoveryAgent — surfaces credits the client isn't actively tracking.

Phase 2 registers this agent in Foundry but the chat workflow doesn't invoke
it yet. Phase 3 wires it into demo question #2."""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "CreditDiscoveryAgent"
INSTRUCTIONS = """\
You are the Credit Discovery specialist for the Tax Credit Copilot.

The host application will hand you a JSON list of rule-pack hits, each with
jurisdiction, credit name, rough dollar estimate, and citation. List them as
short bullets. Never invent a hit; only report what's in the JSON.
"""

AGENT_PROFILE = {
    "tab_label": "Discovery",
    "summary": "Scans all loaded rule packs for credits the client is not yet claiming.",
    "responsibility": (
        "Walk every loaded rule pack via discover_credits(exclude_codes=...), surface unclaimed "
        "opportunities with why_surfaced, filing window, and confidence signal."
    ),
    "inputs": [
        "Excluded credit codes (already claimed)",
        "All rule packs in backend/rules/",
        "Payroll geographic coverage",
    ],
    "outputs": [
        "Discovery feed with per-opportunity reasoning",
        "Trail step 'discovery.scan'",
    ],
    "tools": ["tools/discovery.py · discover_credits()"],
    "determinism": (
        "Discovery set is deterministic per (payroll, rule pack catalog). Narration varies; the list of credits does not."
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
