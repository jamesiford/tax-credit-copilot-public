"""The portal's chat intents, and which tool each one runs. [CH-02]

Pure data, standard library only. Split out of `catalog`, which re-exports all three
names. Two vocabularies are deliberately different: **tools** (`CATALOG`) are the
contract the channel exposes; **chat intents** (`CAPABILITIES`) are what the portal's
router may choose between, each running one tool (`CHAT_INTENT_TOOL`).
"""
from __future__ import annotations

#: Everything the chat can actually answer, and what each one costs.
#:
#: A plan is validated against these names. The router is a language model and
#: will happily invent `trend_analysis` or `client_deep_dive`; an unrecognised
#: intent is DROPPED rather than dispatched, because a made-up intent that
#: silently runs the default pipeline answers a question nobody asked.
CAPABILITIES: dict[str, str] = {
    "book": (
        "who to call ACROSS EVERY CLIENT, ranked by why — the portfolio question. "
        "Needs no client selected; naming one would be the opposite of what was asked."
    ),
    "situation": "why this client is worth calling — bands, programmes, years. Claims only.",
    "eligibility": "the credit figure and headcount for the selected client-year.",
    "at_risk": (
        "which employees ALREADY counted toward the credit sit close enough to a "
        "statutory floor that they could fall out of it — jobs the client could lose."
    ),
    "trend": "how a client has moved across years, and whether they have been eligible since their base year.",
    "multi_state": (
        "which PROGRAMMES across every state one client may qualify for — a rule-pack "
        "scan for the selected client, NOT a view across clients."
    ),
    "discovery": "other programmes the client may qualify for, excluding the one in scope.",
    "simulate": "what-if: hiring, losing, hours or wages against the statutory engine.",
    "explain": "re-narrate the cached calculation trail, step by step.",
}

#: Which intents are about ONE client, and therefore cannot be answered without
#: one selected.
#:
#: The chat used to refuse every question without a client, which made the
#: portfolio question — "who should we reach out to?" — unanswerable from the
#: title bar, where no client is selected BY DESIGN. The refusal itself is
#: right and stays: it exists so nothing silently answers against the default
#: tenant. It just belongs per capability rather than across the whole door.
NEEDS_CLIENT: frozenset[str] = frozenset({
    "situation", "eligibility", "at_risk", "trend", "multi_state",
    "discovery", "simulate", "explain",
})

#: The tool each intent runs. `multi_state` and `discovery` are one scan with
#: different exclusions, so they share a tool.
CHAT_INTENT_TOOL: dict[str, str] = {
    "book": "book_rank",
    "situation": "client_situation",
    "eligibility": "client_eligibility",
    "at_risk": "client_at_risk",
    "trend": "client_trend",
    "multi_state": "client_discovery",
    "discovery": "client_discovery",
    "simulate": "simulate",
    "explain": "calc_walkthrough",
}
