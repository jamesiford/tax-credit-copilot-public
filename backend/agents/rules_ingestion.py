"""RulesIngestionAgent — retrieves GA JTC rules via Web IQ and cites them.

Spec: Part A/A5 + Part D + CALC-11 + GOV-01. This is the agent that produces
the config the calc engine consumes. It NEVER invents a threshold: the Python
orchestrator runs `tools/rules_ingestion.py` (Web IQ retrieval from GA DCA /
GA DOR / O.C.G.A. § 48-7-40), and this agent narrates the retrieved, cited
config. Every value it reports carries a source URL + retrieved-at date.
"""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "RulesIngestionAgent"
INSTRUCTIONS = """\
You are the Rules Ingestion specialist for the Georgia Jobs Tax Credit.

The host application hands you JSON that the rules-ingestion tool retrieved from
trusted PRIMARY sources (Georgia DCA, Georgia DOR, O.C.G.A. § 48-7-40) via Web
IQ. It contains, per parameter: `value`, `authority`, `url`, `retrieved_at`,
`confidence`, and a `verify` flag.

Report the GA JTC rule set in a few short sentences: the weekly-hours bar, the
weekly-wage floor (and its basis — the average weekly wage of Georgia's lowest
county, published annually), the wage basis (all remuneration), the measuring
date, and the per-tier job minimum. For EACH number, cite its authority. If a
parameter is flagged `verify`, say it is pending SME confirmation. Never state a
threshold that is not in the JSON — that is the audit-defensibility story.
"""

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


def build(*, project_client, project_endpoint, credential, model) -> AgentRecord:
    return register_agent(
        project_client=project_client,
        project_endpoint=project_endpoint,
        credential=credential,
        model=model,
        name=NAME,
        instructions=INSTRUCTIONS,
        temperature=0.1,
        profile=AGENT_PROFILE,
    )
