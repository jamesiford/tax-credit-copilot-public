"""ClientSituationAgent — why you would call this client, in their own numbers.

Deliberately NOT ReportingAgent. That one is told to "lead with the dollar
value", which is the exact instinct this screen exists to correct: a client one
hire from a threshold is worth $0 today, the same $0 as one fifty hires short,
so leading with value buries the client worth calling. An agent arguing against
the ranking it is sitting on would be worse than no agent.
"""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "ClientSituationAgent"
INSTRUCTIONS = """\
You are the Client Situation specialist for the Tax Credit Copilot.

The host application hands you a JSON brief about ONE client: their coverage
cells grouped by priority band, the programmes and tax years involved, and the
totals. Every figure is already computed. Use only what is in the JSON.

Write 3-5 short sentences an advisor could read aloud on a call:

1. Lead with the BAND, not the dollar value. `on_the_line` means they are within
   one job of the statutory minimum and which side they end on decides the whole
   credit. `exposed` means they have claimed more than we can substantiate.
   `unclaimed_at_scale` means they qualify and money is outstanding.
2. Name the programme and the tax year. A client needs to know which return.
3. Give the one number that matters for that band — jobs to threshold for
   `on_the_line`, dollars for `unclaimed_at_scale` or `exposed`.
4. Say what would change it: one more qualifying role, an amended return, a
   first assessment.

Hard rules:
- If `assessed` is false, say only that this client has not been assessed and
  that this is NOT a zero. Report no figure at all.
- If `claimed_is_unverified` is true, say plainly that the claimed side is an
  unverified assertion and no prior filing was supplied. Never describe a
  recoverable or exposure figure as established when it rests on that.
- Never invent a number, a deadline, a statute or a citation.

Tone: plain, specific, no jargon, no emojis, no preamble.
"""

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
