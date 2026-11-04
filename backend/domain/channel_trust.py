"""Which channels are trusted with employee-level rows. [RM-02, ADR-009]

A first-party channel is one whose orchestrator renders a person's employee-level rows itself and
shows its model names only: Teams and Microsoft 365 Copilot Chat. Everything else (Copilot Cowork,
a person's own token sent straight to the API, an unknown or missing channel) is treated like
Cowork, whose model reads whatever text a tool returns. The list is positive on purpose: a new
channel is untrusted until somebody adds it here and proves its lanes.

Standard library only; the API and the gateway both read it, so neither can drift from the other.
"""
from __future__ import annotations

FIRST_PARTY_CHANNELS = ("teams", "m365-copilot")
