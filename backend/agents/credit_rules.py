"""CreditRulesAgent — narrates pre-computed credit math."""
from __future__ import annotations

from domain.ai import AgentSpec, ModelRole

from ._prompts import load_instructions


NAME = "CreditRulesAgent"
INSTRUCTIONS = load_instructions("credit_rules")

AGENT_PROFILE = {
    "tab_label": "Credit Rules",
    "summary": "Applies the active rule pack and narrates the credit calculation.",
    "responsibility": (
        "Take the net-new Average Monthly Headcount, look up the per-state rule pack via STATE_TO_PACK, "
        "and report qualifying jobs, annual credit, lifetime credit, and the statutory citation."
    ),
    "inputs": [
        "Net-new Average Monthly Headcount from HeadcountAgent",
        "Detected state code",
        "Rule pack JSON (backend/rules/*.json)",
    ],
    "outputs": [
        "Natural-language calculation summary with citation",
        "Trail step 'credit.apply' with formula + output",
    ],
    "tools": [
        "tools/credit_math.py · apply_one_zero_state_credit() — routes via STATE_TO_PACK; returns no_state_pack=True for TX (no fallback)",
    ],
    "determinism": (
        "Fully deterministic numerically. Agent narrates the tool result; it cannot change the dollar amount."
    ),
}


SPEC = AgentSpec(
    name=NAME, instructions=INSTRUCTIONS, role=ModelRole.NARRATOR,
    temperature=0.2, profile=AGENT_PROFILE,
)
