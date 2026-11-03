"""Keyword routing: which chat intents the words suggest, with no model. [CH-08]

The FALLBACK rather than the primary path: it is what answers when the router is
unavailable or returns nothing usable, and it is why an unconfigured Foundry
project still gives a sensible reply. Standard library only so the channel
orchestrator can use the very same table (it is vendored there), and so the portal
chat and the channel cannot route the same words differently.
"""
from __future__ import annotations

KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("explain", ("walk me through", "how did you", "how do you", "explain",
                 "show your work", "show the calculation", "show me the calculation")),
    # FIRST, and before `multi_state`. "Who should we reach out to" is the
    # portfolio question and must not be captured by a rule-pack scan whose
    # tokens overlap heavily with it.
    ("book", ("who should we", "who do we", "who to call", "which client",
              "which clients", "reach out", "call first", "best client",
              "next best customer", "next best client", "best customer",
              "targeting", "who to target", "should we target", "top target",
              "target list",
              "across our clients", "across the book", "our book",
              "top of the list", "prioriti", "worth contacting")),
    # Before `simulate`: "may fall off" and "at risk" are questions about the
    # CURRENT population, not hypotheticals, and the words overlap heavily.
    ("at_risk", ("fall off", "fall out", "falling off", "at risk", "drop off",
                 "lose eligibility", "losing eligibility", "close to the threshold",
                 "near the threshold", "barely", "marginal", "fragile",
                 "could we lose", "might we lose", "keep them")),
    ("trend", ("trend", "since their base year", "since the base year", "base year",
               "over the years", "year over year", "year-over-year", "history",
               "subsequent years", "each year", "every year", "prior years")),
    ("situation", ("situation", "why would i call", "why call", "overview of this client",
                   "client overview", "where do they stand", "what should i say",
                   "brief me", "worth calling", "why are they")),
    ("simulate", ("what if", "hired", "hire ", "simulate", "what would happen", "next month")),
    ("multi_state", ("portfolio", "every state", "all our states", "all states",
                     "all jurisdictions", "full credit picture", "complete credit picture",
                     "across our footprint", "full picture", "complete picture",
                     "every credit", "all credits", "entire footprint", "multi-state")),
    ("discovery", ("other credits", "other credit", "what else", "discover",
                   "may also qualify", "might we qualify", "additional credits")),
)


def keyword_intents(message: str) -> list[str]:
    """Every intent the words suggest, in call order — not just the first.

    Returns a LIST because one sentence is routinely two questions: "what is
    their trend, and have they been eligible since their base year" is one
    intent, but "brief me on them and what else might they qualify for" is two.
    """
    m = message.lower()
    hits = [name for name, tokens in KEYWORDS if any(t in m for t in tokens)]
    return hits or ["eligibility"]
