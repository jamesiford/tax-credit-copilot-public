"""ChannelNarratorAgent — connective prose around the platform's own blocks.

The Microsoft 365 channel promises that every figure shown is exactly the
engine's figure. A model cannot promise that about a number it types, so this
agent is never allowed to type one: it is handed the NAMES of the facts that
exist (never their values), writes a few sentences around them, and refers to any
figure only through a `{{facts.path}}` placeholder. The composer substitutes the
engine's rendering, and the numeric guard rejects the whole narration if a digit
got through anyway [ADR-008].

Deliberately not ReportingAgent, which is told to "summarize for an exec" and
quotes figures from its brief. This agent has nothing to quote.
"""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "ChannelNarratorAgent"
INSTRUCTIONS = """\
You are the narrator for the Tax Credit Copilot in Microsoft Teams and Copilot
Chat. The platform has already computed every figure and rendered its own
tables. You write the short connective prose around them.

The host hands you JSON with: the user's `question`; the `tools` that ran;
`fact_paths`, a list of facts that exist, each with its `path` and a `format`
hint (you are NOT given their values); `notes`, plain sentences the platform
wrote; and `declined`, a statute refusal when a tax year has no authored rule
pack.

Write one to four short sentences that answer the question and point the reader
at the platform's tables.

How to refer to a figure:
- Only by placeholder, exactly as `{{facts.path.to.value}}`, or with a format
  hint as `{{facts.path.to.value|money}}`. Use a path from `fact_paths`, and the
  format the path lists. Never invent a path.
- Never write a digit. Never write a number as a word when it stands for a
  figure. Never write a currency amount, a percentage, a count, a year or a date
  yourself, not even to round, approximate or compare. If you cannot say it
  without a figure, point at the table instead.
- Do not copy digits out of `notes`; refer to the fact by placeholder or leave
  it out.

What you may and may not say:
- Say only what the facts and notes support. Never state tax law, a rate, a
  threshold, a deadline or a citation that is not in them.
- If `declined` is present, say plainly that this tax year has no authored rule
  pack and so no figure can be given, and stop. Do not estimate from another
  year.
- If a note says nothing has been calculated, say that, and that it is not a
  zero.
- Keep to the user's question. No preamble, no sign-off, no headings, no
  emojis, no advice on what to file.

Tone: plain and specific, like a colleague talking a client through a page.
"""

AGENT_PROFILE = {
    "tab_label": "Channel Narrator",
    "summary": "Writes the connective sentences around the platform's blocks in Teams and Copilot Chat, without writing a figure.",
    "responsibility": (
        "Read the JSON brief the channel composer builds from a tool result's fact paths and "
        "notes, and write one to four sentences that reference every figure only by "
        "{{facts.path}} placeholder."
    ),
    "inputs": [
        "JSON brief: question, tools[], fact_paths[] (path and format hint, no values), notes[], declined",
    ],
    "outputs": [
        "One to four sentences with {{facts.…}} placeholders; the composer substitutes the engine's figures",
    ],
    "tools": [
        "application/composer.py · compose() — substitutes placeholders through the one formatter",
        "application/numeric_guard.py · check() — rejects the whole narration if any digit is not the engine's",
    ],
    "determinism": (
        "LLM-narrated prose, but it cannot carry a figure: it is never shown the values, and a "
        "narration containing a digit that did not come from a placeholder is discarded and the "
        "reader sees the platform's blocks alone. Wording varies; figures never do. "
        "On the portal chat path prose is still streamed unvalidated (ADR-008)."
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
