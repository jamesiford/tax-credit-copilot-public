"""LegislativeMonitorAgent (AI-03) — watches GA programs/wage rates for change.

Spec: Part D / AI-03 + ARCH-03. Reuses the same Web IQ ingestion path as the
RulesIngestionAgent, but in a monitoring mode: it re-probes the trusted GA
source URLs, detects when a designation list or wage table has changed, and
alerts — keeping the cited rules config current with provenance. It replaces
the manual Thomson-Reuters "fire-hose" reading the partner does today.
"""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "LegislativeMonitorAgent"
INSTRUCTIONS = """\
You are the Legislative / Program-Monitoring specialist for Georgia incentives.

The host application hands you JSON from the monitoring run: for each trusted GA
source (DCA Job Tax Credit program, GA DOR, statute) it lists the source URL,
whether it was reachable, when it was last checked, and any detected drift from
the captured config.

Report concisely: which sources were checked, whether anything changed (new
county tier designations, a new annual wage table, a statute amendment), and
what the reviewer should refresh. If nothing changed, say the GA rule set is
current as of the last check. Use only the JSON facts; never invent a change.
"""

AGENT_PROFILE = {
    "tab_label": "Legislative Monitor",
    "summary": "Monitors GA program/wage-rate publications for change and alerts, keeping the cited rules config current with provenance.",
    "responsibility": (
        "Reuse the Web IQ ingestion path to detect changed GA programs, designation lists, and wage rates; pull the "
        "source publications and alert so the RulesIngestionAgent can refresh the cited config (AI-03 / ARCH-03)."
    ),
    "inputs": [
        "Trusted GA source URLs from the cited config",
        "Captured config snapshot (baseline for drift detection)",
    ],
    "outputs": [
        "Per-source reachability + last-checked report",
        "Drift alerts feeding the alert queue",
        "Trail step 'Monitor GA rule sources'",
    ],
    "tools": [
        "tools/rules_ingestion.py · ingest_ga_jtc(live=True) — re-probes each source URL",
        "tools/rules_ingestion.py · provenance_report() — baseline citations to diff against",
    ],
    "determinism": (
        "Reachability + drift detection are deterministic; the agent narrates the result. It cannot fabricate a "
        "rule change — an unreachable source is flagged, not assumed changed."
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
