"""HeadcountAgent — narrates pre-computed statutory Average Monthly Headcount."""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "HeadcountAgent"
INSTRUCTIONS = """\
You are the Headcount specialist for the Tax Credit Copilot.

The host application will hand you JSON with `state`, `average_headcount`,
`prior_period_average_headcount`, and `qualifying_jobs`. In ONE short sentence,
report the current vs prior-year Average Monthly Headcount and the net-new
qualifying jobs in plain language. Use the exact numbers; never invent.
"""

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
