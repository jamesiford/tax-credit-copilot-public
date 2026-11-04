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

from .roster import build_spec

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


SPEC = build_spec("channel_narrator", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
