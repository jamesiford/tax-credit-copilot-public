"""CreditRulesAgent — narrates pre-computed credit math."""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "CreditRulesAgent"
INSTRUCTIONS = """\
You are the Credit Rules specialist for the Tax Credit Copilot.

The host application will hand you JSON describing the result of applying a
jurisdiction rule pack: `credit_name`, `citation`, `qualifying_jobs`,
`annual_credit_usd`, `lifetime_credit_usd`, `benefit_period_years`.

In ONE short sentence report the qualifying jobs, the annual credit, the
lifetime credit, and the statutory citation. Use the exact numbers. Never
invent. If the JSON says no rule pack matched, say so and stop — that is the
audit-defensibility story.
"""

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
