"""CreditDiscoveryAgent — surfaces credits the client isn't actively tracking.

Phase 2 registers this agent in Foundry but the chat workflow doesn't invoke
it yet. Phase 3 wires it into demo question #2."""
from __future__ import annotations

from domain.ai import AgentSpec, ModelRole

from ._prompts import load_instructions


NAME = "CreditDiscoveryAgent"
INSTRUCTIONS = load_instructions("credit_discovery")

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


SPEC = AgentSpec(
    name=NAME, instructions=INSTRUCTIONS, role=ModelRole.NARRATOR,
    temperature=0.2, profile=AGENT_PROFILE,
)
