"""The client review pack: what asks for it, and which capabilities it runs. [RM-10c]

The pack is the read-only half of the `tcc-client-review-pack` skill, for Teams and Copilot Chat: resolve the
client, read the position (the situation, eligibility under both certified methods, the trend, the jobs at risk,
the other programmes), check, and compose. It is a FIXED sequence, so it is a Workflow (`maf_review_pack`) and
not an Agent: no model chooses a step, and none writes a word of the reply.

What it is not, and why (D-131):

- **No what-if step.** A what-if needs a worksite and a size; the size is the reader's and the worksite is read
  from their words or an earlier result, which takes a model. A step that chose either in code would invent it.
  It stays an open question for the Agent, and the pack's reply says so.
- **No data step.** A descriptive question about the payroll data is open Q&A (`data_catalog`, `data_query`).
- **No decisions or changes.** Findings, claim moves and the claim package are the person's decisions, one
  confirmation each: they go through the write Workflow when the person asks, never inside the pack.
- **No walkthrough.** The calculation trail is long; it is one question away ("walk me through it").

Pure functions of the reader's words and the catalog's chat-intent table; no framework, no gateway, no model.
"""
from __future__ import annotations

import re

from application.capabilities.catalog_intents import CHAT_INTENT_TOOL

MODE = "review_pack"
_PACK = re.compile(r"\breview\s+pack\b|\b(?:client|credit)\s+review\b|\bclient\s+briefing\b", re.IGNORECASE)
#: The chat intents the pack runs, in the order the reply shows them; each names its tool through the catalog.
POSITION = ("situation", "eligibility", "trend", "at_risk", "discovery")
#: Every step once, and the second certified method of eligibility: the sequence is fixed, so this is its whole budget.
CALL_LIMIT = len(POSITION) + 1


def wants_review_pack(text: str) -> bool:
    """True when the reader asks for the pack by name ("review pack for X", "client review", "client briefing")."""
    return bool(_PACK.search(text or ""))


def step_tools() -> list[str]:
    """The catalog tools the pack runs, in order."""
    return [CHAT_INTENT_TOOL[intent] for intent in POSITION]
