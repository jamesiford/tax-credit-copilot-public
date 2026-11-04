"""LegislativeMonitorAgent (AI-03) — watches GA programs/wage rates for change.

Spec: Part D / AI-03 + ARCH-03. Reuses the same Web IQ ingestion path as the
RulesIngestionAgent, but in a monitoring mode: it re-probes the trusted GA
source URLs, detects when a designation list or wage table has changed, and
alerts — keeping the cited rules config current with provenance. It replaces
the manual Thomson-Reuters "fire-hose" reading the partner does today.
"""
from __future__ import annotations

from .roster import build_spec

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


SPEC = build_spec("legislative_monitor", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
