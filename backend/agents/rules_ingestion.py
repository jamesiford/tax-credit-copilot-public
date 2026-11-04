"""RulesIngestionAgent — retrieves GA JTC rules via Web IQ and cites them.

Spec: Part A/A5 + Part D + CALC-11 + GOV-01. This is the agent that produces
the config the calc engine consumes. It NEVER invents a threshold: the Python
orchestrator runs `tools/rules_ingestion.py` (Web IQ retrieval from GA DCA /
GA DOR / O.C.G.A. § 48-7-40), and this agent narrates the retrieved, cited
config. Every value it reports carries a source URL + retrieved-at date.
"""
from __future__ import annotations

from .roster import build_spec

AGENT_PROFILE = {
    "tab_label": "Rules Ingestion",
    "summary": "Retrieves GA JTC thresholds/rules from primary sources via Web IQ and serialises them, with citations, into the config the engine reads.",
    "responsibility": (
        "Own the GA rule set. Retrieve wage/hours thresholds, magical pay date, industry/zone eligibility, and job "
        "targets from GA DCA / GA DOR / statute; serialise them WITH per-value provenance into "
        "data/rules_ingested/ga_jtc.json. No GA threshold is hand-entered into the engine (CALC-11 / GOV-01)."
    ),
    "inputs": [
        "Trusted GA source URLs (DCA Job Tax Credit program, GA DOR, O.C.G.A. § 48-7-40)",
        "Prior captured config (drift detection)",
    ],
    "outputs": [
        "Cited config data/rules_ingested/ga_jtc.json (per-value source + retrieved_at + confidence)",
        "Provenance report consumed by /api/rules/ingested/GA and the Eligibility Validation view",
        "Trail step 'Ingest GA JTC rules (Web IQ)'",
    ],
    "tools": [
        "tools/rules_ingestion.py · ingest_ga_jtc(live=) — Web IQ retrieval + serialise",
        "tools/rules_ingestion.py · ingested_one_zero() — feeds the eligibility floors into credit_math.load_pack_one_zero",
        "tools/rules_ingestion.py · provenance_report() — GOV-01 per-value citations",
    ],
    "determinism": (
        "Config values are retrieved + serialised deterministically; the agent narrates them and cannot alter a "
        "threshold. Live retrieval flags unreachable sources verified=False for the human checkpoint."
    ),
}


SPEC = build_spec("rules_ingestion", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
