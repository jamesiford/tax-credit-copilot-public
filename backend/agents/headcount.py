"""HeadcountAgent — narrates pre-computed statutory Average Monthly Headcount."""
from __future__ import annotations

from domain.ai import AgentSpec, ModelRole

from ._prompts import load_instructions


NAME = "HeadcountAgent"
INSTRUCTIONS = load_instructions("headcount")

AGENT_PROFILE = {
    "tab_label": "Headcount Calc",
    "summary": "Narrates net-new Average Monthly Headcount versus the prior-year baseline.",
    "responsibility": (
        "Report current-year and prior-year statutory Average Monthly Headcount and the net-new "
        "qualifying jobs for the targeted jurisdiction, from the One/Zero Base Calculation engine."
    ),
    "inputs": [
        "JSON brief from tools/portfolio.chat_state_credit()",
        "Active rule pack one_zero eligibility floors (min_weekly_hours, min_weekly_wages, thresholds_by_year)",
    ],
    "outputs": [
        "Natural-language headcount summary",
        "Trail steps from the One/Zero engine (per-employee 1/0.5/0 → Average Monthly Headcount → net-new)",
    ],
    "tools": ["tools/portfolio.py · chat_state_credit() (statutory One/Zero engine)"],
    "determinism": (
        "Eligibility floors are pinned to the rule pack JSON. Same payroll + same pack → identical Average Monthly Headcount across runs."
    ),
}


SPEC = AgentSpec(
    name=NAME, instructions=INSTRUCTIONS, role=ModelRole.NARRATOR,
    temperature=0.2, profile=AGENT_PROFILE,
)
