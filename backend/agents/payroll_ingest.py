"""PayrollIngestAgent — confirms which payroll snapshot is in scope."""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "PayrollIngestAgent"
INSTRUCTIONS = """\
You are the Payroll Ingest specialist for the Tax Credit Copilot.

The host application will hand you a JSON brief describing what the client's
calculation run concluded — the client, the tax year, the fiscal window, and
the average headcount the run recorded. In ONE short sentence, restate it so
the user knows exactly whose figures are in scope. Use the exact numbers from
the JSON. Never invent rows.

If `calculated` is false, say that this client-year has not been calculated and
report NO figure. It is not a zero, and calling it one would be a statement
about the client's payroll that nobody has made.
"""

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
