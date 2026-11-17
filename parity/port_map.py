"""Generate ``dotnet/docs/port-map.md`` (stage DS1).

The classification table below is the human verdict; the import evidence, line
counts, call-path flags and the specifying Python tests are computed from the
source so the map cannot drift from it. ``--check`` fails when the committed
file is stale or when any module under domain/ or tools/ lacks a verdict.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dotnet" / "docs" / "port-map.md"
TESTS = inventory.BACKEND / "tests"

PC, PM, AD, SC, PR, WR, AG, OT = (
    "pure-calculation", "pure-model", "adapter", "script", "private-reference", "web-retrieval", "agent", "other",
)
D, A, I, X = "Domain", "Application", "Infrastructure", "out of scope"
IN = "slice-domain"

# module -> (classification, target project, reason)
VERDICT: dict[str, tuple[str, str, str]] = {
    "domain": (PM, D, "package marker"),
    "domain.calculation": (PM, D, "package marker"),
    "domain.ai": (AG, X, "model ports and specs; AI slice"),
    "domain.ai_errors": (AG, X, "AI error taxonomy; AI slice"),
    "domain.channel": (OT, X, "Microsoft 365 channel models; channel slice"),
    "domain.channel_trust": (OT, X, "channel trust marker; channel slice"),
    "domain.calculation.fiscal": (PC, D, "stdlib only; fiscal windows and tax-year convention"),
    "domain.calculation.floors": (PM, D, "stdlib only; StatutoryFloors value object"),
    "domain.calculation.headcount": (PC, D, "stdlib only; average headcount over a window"),
    "domain.calculation.onezero": (PC, D, "stdlib only; the certified engine (spike ported the core)"),
    "domain.calculation.performance": (PC, D, "stdlib only; performance roll-ups"),
    "domain.calculation.proximity": (PC, D, "stdlib only; near-miss and fragile cohorts"),
    "domain.calculation.reconciliation": (PC, D, "stdlib only; reconciliation arithmetic"),
    "domain.calculation.rollups": (PC, D, "stdlib only; roll-up sums"),
    "domain.calculation.trail": (PC, D, "stdlib only; ContextVar trail recorder and SHA-256"),
    "domain.claims": (PC, D, "stdlib only; claim position, bands, trend"),
    "domain.coverage": (PC, D, "imports domain.claims only; totals, matrix, situation"),
    "domain.findings": (PM, D, "stdlib only; resolution record"),
    "domain.program_drafts": (PM, D, "stdlib only; draft lifecycle and hashing"),
    "domain.programs": (PM, D, "stdlib only; registry entry models"),
    "domain.runs": (PM, D, "stdlib only; batch state machine"),
    "domain.warehouse": (PM, D, "stdlib only; manifest, override records and repository Protocols"),
    "tools": (PM, X, "package marker"),
    "tools.backfill_gold": (SC, X, "operator script (__main__, warehouse writes)"),
    "tools.baseyear": (PC, D, "imports domain.calculation.trail only; base-year tranches"),
    "tools.brief_format": (AG, X, "pre-formatting helpers for agent briefs; agents slice"),
    "tools.build_approval_package": (OT, X, "xlsx output; application slice"),
    "tools.canonical": (PC, D, "csv/path reads isolated to loaders; canonical mapping and QC; imports data.sites"),
    "tools.check_certified_live": (SC, X, "live-Fabric check script"),
    "tools.check_gold_grain": (SC, X, "check script"),
    "tools.code_standards": (SC, X, "repository lint ratchet"),
    "tools.code_standards.baseline": (SC, X, "repository lint ratchet"),
    "tools.code_standards.duplicates": (SC, X, "repository lint ratchet"),
    "tools.code_standards.metrics": (SC, X, "repository lint ratchet"),
    "tools.create_run_method_summary": (SC, X, "DDL script"),
    "tools.credit_math": (PC, D, "rule-pack access plus credit arithmetic; pack access goes behind IRulePackSource"),
    "tools.designation": (PC, D, "imports data.designations (prototype data) and trail"),
    "tools.discovery": (PC, D, "view over portfolio builder; depends on tools.portfolio"),
    "tools.fabric_source": (AD, I, "Fabric/OneLake reader"),
    "tools.forecast": (PC, D, "engine plus credit math; run-rate projection"),
    "tools.gold_projection": (PC, D, "pure by its own contract: data in, rows out"),
    "tools.grid_filter": (PC, D, "filter grammar parser and SQL-predicate compiler; no connection"),
    "tools.negotiated": (PC, D, "negotiated wage-standard resolver"),
    "tools.one_zero_pack": (PC, D, "builds the One/Zero pack view from a rule pack"),
    "tools.pack_lookup": (PC, D, "program/state to pack-file resolution"),
    "tools.pack_validation": (PC, D, "semantic rules in Domain; JSON Schema through a library"),
    "tools.page_brief": (AG, X, "page briefs for PageSummaryAgent; agents slice"),
    "tools.payroll": (AD, I, "reads data/payroll.csv"),
    "tools.portfolio": (OT, A, "reads Gold through application.services; builds the portfolio view; application slice"),
    "tools.portfolio_brief": (AG, X, "portfolio brief for the summary agent; agents slice"),
    "tools.preview_sample": (AD, I, "reads the committed sample CSV"),
    "tools.program_credit": (PC, D, "program-keyed credit; stdlib plus registry"),
    "tools.program_registry": (PC, D, "registry loader (file I/O behind IRulePackSource) and views"),
    "tools.program_scaffold": (SC, X, "writes draft files to disk; authoring tool"),
    "tools.purge_test_claims": (SC, X, "SQLite purge script"),
    "tools.qc": (PC, D, "stdlib plus trail; QC classification and hashing"),
    "tools.reap_stranded_runs": (SC, X, "operator script"),
    "tools.reconcile": (PC, D, "reconciliation helper"),
    "tools.reference_compare": (PR, X, "needs the private reference extract; openpyxl"),
    "tools.reference_identity": (PR, X, "private reference"),
    "tools.reference_onezero": (PR, X, "private reference"),
    "tools.reference_runner": (PR, X, "private reference; subprocess"),
    "tools.reference_source": (PR, X, "private reference"),
    "tools.reference_step1": (PR, X, "private reference"),
    "tools.reference_workspace": (PR, X, "private reference; subprocess"),
    "tools.rules_ingestion": (WR, X, "urllib web retrieval; agents slice"),
    "tools.simulation": (PC, D, "what-if computation; request models are presentation"),
    "tools.tokens": (PC, D, "SHA-256 record-token derivation"),
    "tools.triggers": (PC, D, "snapshot diff engine"),
    "tools.unit_trend": (PC, D, "unit trend over base-year tranches"),
    "tools.verify_gold_reads": (SC, X, "verification script"),
    "tools.verify_reference_independent": (SC, X, "independent verifier; private extract"),
    "tools.verify_unit_filter": (SC, X, "verification script"),
    "tools.webiq": (WR, X, "urllib web retrieval; agents slice"),
}

# application modules on the calculation path
APP_VERDICT: dict[str, tuple[str, str, str]] = {
    "application.assessment": (PC, A, "assessment service over engine results"),
    "application.assessment_claims": (PC, A, "claim construction from assessment"),
    "application.assessment_inputs": (PM, A, "assessment inputs"),
    "application.commands.assess_client": (OT, A, "mediator command; Application slice"),
    "application.commands.run_client_calculation": (OT, A, "the handler under study; Application slice (capstone drives it)"),
    "application.gold_ports": (PM, A, "port declarations"),
    "application.gold_read_port": (PM, A, "port declaration"),
    "application.identity": (OT, A, "caller identity; Application slice"),
    "application.mediator": (OT, A, "pipeline; Application slice"),
    "application.mediator_audit": (OT, A, "audit; Application slice"),
    "application.open_year": (PC, D, "open-year predicate; pure, candidate for Domain"),
    "application.payroll_rows": (PC, A, "payroll row reader; ordinary errors"),
    "application.program_defaults": (PC, A, "program defaults per state"),
    "application.qc_resolutions": (PC, A, "QC resolution application"),
    "application.queries._client_run": (PC, A, "resolve statute and client run"),
    "application.queries.get_unit_trend": (PC, A, "unit trend query helpers imported by the writer"),
    "application.runs.fingerprint": (PC, A, "run fingerprint hashing"),
    "application.services": (PM, A, "service locator names"),
    "application.source_ports": (PM, A, "payroll port declarations"),
}


# Status of every in-scope module after the slice: ported, partial (pure parts only), pending.
PARTIAL = {
    "tools.credit_math": "pure parts; pack access behind IRulePackSource; pydantic models out",
    "tools.simulation": "computation only; request models out",
    "tools.canonical": "mapping and RowsAdapter; CSV adapter in Infrastructure with documented limits",
    "application.queries.get_unit_trend": "the four pure helpers the writer imports",
    "application.assessment": "pure assessment over engine results (ClientAssessment)",
    "application.assessment_claims": "claim construction (ClientAssessment)",
    "application.payroll_rows": "pure row helpers (PayrollRows)",
    "application.program_defaults": "pure program/state defaults (ProgramDefaults)",
    "application.queries._client_run": "resolve_statute and resolve_client_run (ClientRunResolver)",
    "application.runs.fingerprint": "RunFingerprint",
    "application.qc_resolutions": "QcResolutions",
}
PENDING = {
    "tools.discovery": "depends on tools.portfolio (Application slice); deferred",
    "application.gold_ports": "port declarations: replaced by the capturing IGoldWriter seam",
    "application.gold_read_port": "port declaration for the read side; Application slice",
    "application.source_ports": "port declarations; Application slice",
    "application.services": "service locator names; Application slice",
}


def status_of(name: str, verdict: tuple[str, str, str]) -> str:
    if verdict[0] not in (PC, PM) or verdict[1] not in (D, A):
        return "out"
    if name in PENDING:
        return "pending: " + PENDING[name]
    if name in PARTIAL:
        return "partial: " + PARTIAL[name]
    return "ported"


def tests_for(module: str) -> list[str]:
    pat = re.compile(rf"^\s*(?:from\s+{re.escape(module)}\s+import|import\s+{re.escape(module)}\b|from\s+{re.escape(module.rpartition('.')[0])}\s+import\s+[^\n]*\b{re.escape(module.rpartition('.')[2])}\b)", re.M)
    return sorted(p.name for p in TESTS.glob("test_*.py") if pat.search(p.read_text(encoding="utf-8", errors="replace")))


def render() -> tuple[str, list[str]]:
    mods = {m["module"]: m for m in (inventory.scan(p) for p in sorted(inventory.BACKEND.rglob("*.py"))
                                    if "tests" not in p.parts and "__pycache__" not in p.parts)}
    index = mods
    calc = inventory.reachable(["application.commands.run_client_calculation"], index)
    cq = inventory.reachable([m for m in index if m.startswith(("application.commands.", "application.queries."))], index)
    rows, missing, tally = [], [], []
    for name in sorted(index):
        if name.startswith("domain") or name.startswith("tools"):
            v = VERDICT.get(name)
        elif name in APP_VERDICT:
            v = APP_VERDICT[name]
        else:
            continue
        if v is None:
            missing.append(name)
            continue
        m = index[name]
        path = "calc" if name in calc else ("cmd/query" if name in cq else "-")
        io = ",".join(m["io"]) or "-"
        internal = ",".join(sorted({i.split(".")[0] + "." + i.split(".")[1] if "." in i else i for i in m["internal"]})) or "-"
        tst = ", ".join(tests_for(name)) or "-"
        st = status_of(name, v)
        if st != "out":
            tally.append((name, m["lines"], st.split(":")[0]))
        rows.append(f"| `{name}` | {m['lines']} | {v[0]} | {v[1]} | {path} | io: {io}; imports: {internal} | {v[2]} | {st} | {tst} |")
    head = (
        "# Port map (DS1)\n\n"
        "Generated by `parity/port_map.py` from the Python source; do not edit by hand. Lines are physical lines.\n"
        "`path`: *calc* = reachable from `run_client_calculation`; *cmd/query* = reachable from another command or query.\n"
        "`io` lists I/O-signalling third-party imports found by AST. `internal` lists first-party packages imported.\n\n"
        "| Python module | Lines | Classification | Target | Path | Import evidence | Verdict reason | Status | Python tests |\n"
        "|---|---:|---|---|---|---|---|---|---|\n"
    )
    total = sum(n for _, n, _ in tally)
    done = sum(n for _, n, s in tally if s == "ported")
    part = sum(n for _, n, s in tally if s == "partial")
    pend = sum(n for _, n, s in tally if s == "pending")
    count = lambda kind: sum(1 for *_, s in tally if s == kind)  # noqa: E731
    summary = (
        "\n## In-scope summary\n\n"
        f"In-scope Python lines: {total}. Fully ported: {done} ({100 * done / total:.1f}%). "
        f"Partially ported (pure parts only): {part} ({100 * part / total:.1f}%). Pending: {pend} ({100 * pend / total:.1f}%).\n"
        f"Modules: {count('ported')} ported, {count('partial')} partial, {count('pending')} pending.\n"
    )
    return head + "\n".join(rows) + "\n" + summary, missing


def main() -> int:
    text, missing = render()
    if missing:
        print("unclassified:", *missing, sep="\n  ")
        return 1
    if "--check" in sys.argv:
        return 0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
