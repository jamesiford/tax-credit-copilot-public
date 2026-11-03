"""The agent roster. [AI-02]

Single source of truth for which agents ship: add an agent by creating a module
under `backend/agents/` that exports `NAME`, `INSTRUCTIONS`, `AGENT_PROFILE` and
`SPEC`, its prompt under `agents/prompts/`, and appending it to `list_agent_modules`.

This module imports NO SDK. Publishing and running an agent is the provider's job
(`infrastructure/ai/`), driven by the specs this roster yields.
"""
from __future__ import annotations

from domain.ai import AgentSpec, supports_temperature

#: Kept under its old name: callers and tests import it from here.
_supports_temperature = supports_temperature


def list_agent_modules():
    """Every agent module, in roster order."""
    from . import (  # noqa: PLC0415 — deferred to avoid circular import
        channel_narrator,
        client_situation,
        credit_discovery,
        credit_rules,
        exception_report,
        headcount,
        legislative_monitor,
        orchestrator,
        page_summary,
        payroll_ingest,
        reporting,
        rules_ingestion,
    )
    return [
        orchestrator, payroll_ingest, headcount, credit_rules, credit_discovery, client_situation,
        page_summary, reporting, rules_ingestion, exception_report, legislative_monitor, channel_narrator,
    ]


def all_specs() -> list[AgentSpec]:
    """The roster as data, for the spec registry and the catalog."""
    return [module.SPEC for module in list_agent_modules()]
