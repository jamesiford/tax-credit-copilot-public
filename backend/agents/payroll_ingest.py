"""PayrollIngestAgent — confirms which payroll snapshot is in scope."""
from __future__ import annotations

from .roster import build_spec

AGENT_PROFILE = {
    "tab_label": "Payroll Ingest",
    "summary": "Narrates the run the orchestrator read, and whose it is.",
    "responsibility": (
        "Read the JSON brief built by tools/portfolio.chat_client_context() and describe "
        "the client, tax year, fiscal window and recorded average headcount."
    ),
    "inputs": [
        "JSON brief: selected_client_id, selected_tax_year, fiscal_window, "
        "average_headcount, calculated, run_id, source = tcc_gold",
    ],
    "outputs": [
        "Natural-language summary streamed to the chat drawer",
        "Trail step 'payroll.snapshot' recorded by the Python tool",
    ],
    "tools": ["tools/portfolio.py · chat_client_context() — reads tcc_gold, no payroll replay"],
    "determinism": (
        "Tool output is deterministic (it reads the run's own stored figures). Agent text "
        "varies; numbers in the prompt are pinned by the tool."
    ),
}


SPEC = build_spec("payroll_ingest", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
