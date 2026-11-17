"""Emit fixed-schema metadata; native payloads and subprocess diagnostics never become evidence."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from admission import HERE, ORACLE, ROOT, oracle_preflight

DOCS = ROOT / "dotnet" / "docs"
ARTIFACTS = ROOT / "dotnet" / "artifacts" / "w4-integration"
NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


def write(name: str, document: dict) -> None:
    (DOCS / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def command(arguments: list[str], seconds: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, cwd=ROOT / "dotnet", capture_output=True,
                          timeout=seconds, check=False)


def trx(directory: str) -> tuple[dict, set, set]:
    totals, passed, failed, suites = Counter(), set(), set(), {}
    paths = sorted((ARTIFACTS / "gates" / directory).glob("*.trx"))
    if not paths:
        raise RuntimeError("Missing test evidence.")
    for path in paths:
        root = ET.parse(path).getroot()
        counter = root.find("t:ResultSummary/t:Counters", NS)
        if counter is None:
            raise RuntimeError("Missing test counters.")
        values = {key: int(counter.get(key, "0")) for key in ("total", "passed", "failed", "notExecuted")}
        totals.update(values)
        method = root.find(".//t:TestMethod", NS)
        if method is not None:
            suite = method.get("className", "").split(".Tests", 1)[0] + ".Tests"
            suites[suite] = values
        for result in root.findall(".//t:UnitTestResult", NS):
            if result.get("outcome") == "Passed":
                passed.add(result.get("testName"))
            elif result.get("outcome") == "Failed":
                failed.add(result.get("testName"))
    return {"totals": dict(totals), "suites": suites}, passed, failed


def gates() -> None:
    commands = {
        "format": ["dotnet", "format", "TaxCredit.slnx", "--verify-no-changes", "--no-restore", "--verbosity", "quiet"],
        "release_build": ["dotnet", "build", "TaxCredit.slnx", "-c", "Release", "--nologo", "-v", "quiet"],
        "shadow_build": ["dotnet", "build", "tests\\TaxCredit.Shadow.Tests\\TaxCredit.Shadow.Tests.csproj",
                         "-c", "Release", "--nologo", "-v", "quiet"],
        "shadow_format": ["dotnet", "format", "spikes\\shadow\\TaxCredit.Shadow.csproj",
                          "--verify-no-changes", "--no-restore", "--verbosity", "quiet"],
        "shadow_tests": ["dotnet", "test", "tests\\TaxCredit.Shadow.Tests\\TaxCredit.Shadow.Tests.csproj",
                         "-c", "Release", "--no-build", "--nologo", "--logger", "trx;LogFileName=shadow-final.trx",
                         "--results-directory", "artifacts\\w4-integration\\gates\\shadow-final", "-v", "quiet"],
    }
    results = {}
    for name, arguments in commands.items():
        started = time.monotonic()
        result = command(arguments)
        results[name] = {"passed": result.returncode == 0, "ms": round((time.monotonic() - started) * 1000, 3)}
        if result.returncode:
            write("integration-gates.json", {"commands": results, "verdict": "failed"})
            raise RuntimeError("Final observer gate failed; diagnostics retained only in memory.")
    fast, _, _ = trx("fast")
    heavy, passed, failed = trx("heavy")
    repaired, repair_passed, _ = trx("heavy-repair")
    shadow, _, _ = trx("shadow-final")
    python = command([str(ORACLE), "-B", str(HERE / "run_tests.py")])
    guard = command(["dotnet", "run", "--no-build", "-c", "Release", "--project",
                     "spikes\\shadow\\TaxCredit.Shadow.csproj", "--", "--self-test"])
    report = {"commands": results, "full_fast": fast, "full_heavy_initial": heavy,
              "heavy_prerequisite_repair": repaired, "final_shadow": shadow,
              "distinct_heavy_passed": len(passed | repair_passed), "remaining_heavy_failed": len(failed - repair_passed),
              "heavy_monolithic_initial_pass": False,
              "heavy_setup": "Three tests launch fixed Debug API/Worker DLLs; build those prerequisites, then targeted rerun. No product/test edits.",
              "python_boundary": json.loads(python.stdout), "guard": json.loads(guard.stdout),
              "scope": "Full fast before final observer extensions; final Shadow rerun covers current code/Python. Product source unchanged."}
    if (python.returncode or guard.returncode or report["guard"] !=
            {"verdict": "passed", "inherited_fixtures": 31, "templates": 3, "ownership_cases": 3}
            or report["remaining_heavy_failed"]
            or report["distinct_heavy_passed"] != heavy["totals"]["total"]):
        raise RuntimeError("Final evidence is not green.")
    report["verdict"] = "passed-with-disclosed-initial-heavy-setup-failures"
    write("integration-gates.json", report)
    print(json.dumps({"gates": report["verdict"], "fast": fast["totals"],
                      "heavy_distinct_passed": report["distinct_heavy_passed"], "python": report["python_boundary"]}))


def capture_live() -> None:
    check = os.environ.get("SHADOW_CAPACITY_CHECK")
    if not check or not Path(check).is_file():
        raise RuntimeError("Set SHADOW_CAPACITY_CHECK to the capacity admission script before capturing live evidence.")
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([str(ORACLE), "-B", str(HERE / "observe.py"), "--live"], cwd=ROOT / "dotnet",
                            env=environment, capture_output=True, timeout=180, check=False)
    document = json.loads(result.stdout)
    if result.returncode or document.get("verdict") == "failed":
        raise RuntimeError("Safe live observer did not complete.")
    document["classification"] = "Current live approval/admission; data comparisons unmeasured unless admitted per group"
    document["observed_utc"] = datetime.now(timezone.utc).isoformat()
    write("integration-live.json", document)
    print(json.dumps({"admission": document.get("admission"), "attempted": sum(
        row["attempted"] for row in document.get("groups", {}).values())}))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_fingerprint() -> str:
    paths = [path for folder in (HERE, ROOT / "dotnet" / "tests" / "TaxCredit.Shadow.Tests")
             for path in folder.rglob("*") if path.suffix in (".py", ".cs", ".json", ".csproj")]
    content = "\n".join(str(path.relative_to(ROOT)) + ":" + digest(path) for path in sorted(paths))
    return hashlib.sha256(content.encode()).hexdigest()


def provenance() -> None:
    source = command(["git", "diff", "--name-only", "006760b", "--", "src", "..\\backend", "..\\contract"])
    binaries = {}
    for name in ("Api", "Gateway", "Worker", "Orchestrator", "Shadow"):
        path = ROOT / "dotnet" / "artifacts" / "bin" / ("TaxCredit." + name) / "release" / ("TaxCredit." + name + ".dll")
        if not path.is_file():
            raise RuntimeError("Missing Release binary provenance.")
        binaries[name] = {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
    runtimes = command(["dotnet", "--list-runtimes"]).stdout.decode().splitlines()
    runtimes = [line.split()[:2] for line in runtimes if line.split()[0] in
                ("Microsoft.NETCore.App", "Microsoft.AspNetCore.App") and line.split()[1].startswith("10.")]
    document = {"observed_utc": datetime.now(timezone.utc).isoformat(), "product_revision": "006760b",
                "product_and_contract_diff_empty": source.returncode == 0 and not source.stdout.strip(),
                "observer_source_sha256": code_fingerprint(),
                "observer_commit": command(["git", "rev-parse", "--short", "HEAD"]).stdout.decode().strip(),
                "release_binaries": binaries,
                "sdk": command(["dotnet", "--version"]).stdout.decode().strip(), "net10_installed_runtimes": runtimes,
                "oracle": {"implementation": platform.python_implementation(), "version": platform.python_version(),
                           "this_worktree_import": oracle_preflight()},
                "topology": {"baseline": "ordinary native API and independent standalone gateway, sequential, no API dependency for gateway",
                             "paired": "ordinary Python harness/ASGI and native API on loopback; separate state",
                             "cross_surface": "ordinary API plus independent in-process-composed gateway; separate state",
                             "workers": "No Worker during reset/replay; inherited finite Worker tests only in isolated test stores"},
                "providers": {"observed": ["synthetic CSV/seed", "SQLite", "local artifacts", "scripted AI/transports"],
                              "unmeasured": ["native Fabric source/Gold/ops", "Blob", "real exporter", "live Foundry/Entra-bound ingress"]},
                "classification": "isolated synthetic hosts; current live admission only, no private payloads",
                "approval_capacity": json.loads((DOCS / "integration-live.json").read_text())["admission"],
                "native_grants": "unproved; permission/fingerprint/data stages not reached",
                "private_reference_certified": False, "deployments_or_traffic_changes": 0}
    if not document["product_and_contract_diff_empty"] or not document["oracle"]["this_worktree_import"]:
        raise RuntimeError("Provenance boundary changed.")
    write("integration-provenance.json", document)


def lifecycle(group: str, route: str) -> str:
    if group == "workspace_sealed":
        return "all eleven unavailable; reference owner"
    if group == "gateway":
        return "gateway/canonical producer/audit/session/ticket authority"
    if group == "ai":
        return "canonical producer/narration/conversation authority"
    if "/program-drafts" in route:
        return "draft-version/review/export lifecycle"
    if group == "drafts_runs":
        return "program/run/override/queue/Worker/Gold/manifest authority"
    if "/packages" in route or "/artifacts/" in route:
        return "package-generation/metadata/download/audit lifecycle"
    if group == "claims_artifacts_rules":
        return "claims/rules/findings plus accepted run destination"
    return "accepted stored read/source/statute; writes remain coupled"


def routing_table() -> None:
    groups = json.loads((DOCS / "route-groups.json").read_text())["groups"]
    rows = [{"operation": route, "producer": group, "lifecycle": lifecycle(group, route),
             "authority": "retain-existing-no-traffic-change",
             "future_host": "standalone gateway" if group == "gateway" else "API"}
            for group, routes in groups.items() for route in routes]
    if len(rows) != 110 or len({row["operation"] for row in rows}) != 110:
        raise RuntimeError("Route inventory changed.")
    write("integration-route-ownership.json", {"source": "route-groups.json", "inventory_operations": len(rows),
                                             "operations": rows, "additional_hosted_surface": "POST /responses: orchestrator; retain existing"})
    marker = "<!-- W4-ROUTE-TABLE -->"
    path = DOCS / "CUTOVER-RUNBOOK.md"
    lines = ["", "| Method and exact template | Producer | Coupled lifecycle / retained authority |", "|---|---|---|"]
    lines += [f"| `{row['operation']}` | {row['producer']} | {row['lifecycle']}; **retain existing** |" for row in rows]
    lines += ["| `POST /responses` (outside captured inventory) | orchestrator | Whole conversation/confirmation; **retain existing** |", ""]
    path.write_text(path.read_text(encoding="utf-8").split(marker)[0] + marker + "\n" + "\n".join(lines), encoding="utf-8")


def safety() -> None:
    results = json.loads((DOCS / "integration-gates.json").read_text())
    report = {"guard": results["guard"], "tests": results["python_boundary"], "xunit": results["final_shadow"],
              "negative_boundary": ["forbidden SQL/mutations before dispatch", "unknown URL/SQL/transport option refusal",
                                   "sentinel keys/URLs/filenames/header/error data absent from diagnostics",
                                   "no payload open/temp-file or raw-diff serialization in bridge",
                                   "strict money/type/status/null/presence/order mutations detected",
                                   "ordered ZIP members/content and header/body integrity retained",
                                   "trail/canonical/per-file manifest hashes not container exempt",
                                   "byte/row/header/compression/deadline bounds; partial/outage/drift denominators",
                                   "effective protected write rights refused; account fingerprint parameter bound"],
              "scratch": {"used_live": False, "live_created_by_observer": 0, "live_cleanup_needed": False,
                          "native_metadata_enumeration": "unmeasured; no claim that shared schema is empty",
                          "synthetic_finally": {"owned_removed": 1, "shared_preserved": 1},
                          "synthetic_recovery": "failed drop retained, replaced object refused, ledger restored, foreign invocation refused"},
              "side_effects": {"protected_schema_source_or_blob_writes_dispatched": 0, "live_audited_gateway_calls": 0,
                               "live_ticket_redemptions": 0, "live_models_or_graph_diagnostics": 0},
              "boundary": "Only isolated synthetic hosts may write raw logs/reports; mandatory server audit/auth never disabled for live."}
    write("integration-safety.json", report)


def main() -> None:
    if sys.argv[1:] == ["--gates"]:
        gates()
    elif sys.argv[1:] == ["--capture-live"]:
        capture_live()
    elif sys.argv[1:] == ["--write"]:
        provenance()
        routing_table()
        safety()
        print('{"metadata":"written","traffic_changes":0}')
    else:
        raise SystemExit("Use --gates, --capture-live or --write.")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - metadata/live admission must not render native diagnostics or paths
        print('{"verdict":"evidence-generation-failed"}')
        raise SystemExit(1) from None
