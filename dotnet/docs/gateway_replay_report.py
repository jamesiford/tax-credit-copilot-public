"""Read-only W3 policy diagnostic; the public comparator and raw reports stay unchanged."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from convergence_board import covering, numeric_change, tolerated


def global_tolerance(failure: dict, status: int) -> bool:
    path = failure["path"]
    if path.startswith(("facts.", "result.structuredContent.facts.")):
        return False
    if tolerated(failure, status):
        return True
    if failure["category"] == "value" and (path == "error.message" or path.endswith(".error.message")):
        return True  # MCP tool refusals travel inside a successful HTTP response.
    if failure["category"] != "value" or not re.fullmatch(r"result\.content\[\d+\]\.text", path):
        return False
    pattern = r"^The request did not go through \(([^)]+)\): "
    before = re.match(pattern, failure.get("expected", ""))
    after = re.match(pattern, failure.get("actual", ""))
    return bool(before and after and before[1] == after[1])


def durable_counter(failure: dict, entries: list[dict]) -> bool:
    return any(entry.get("finding") == "F-18" for entry in entries) and bool(re.search(
        r"(?:^|\.)(?:preview|dry_run_summary)\.(?:never_run|skip_coverage|skip_candidates_upper_bound)$",
        failure["path"]))


def diagnostic(root: Path, raw: Path) -> dict:
    entries = [entry for path in sorted((root / "dotnet" / "docs" / "improvements").glob("*.json"))
               for entry in json.loads(path.read_text(encoding="utf-8-sig")).get("improvements", [])]
    scenarios, unresolved, numeric_rejections = [], [], []
    hits = Counter()
    for path in sorted(raw.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for scenario in report["scenarios"]:
            name = scenario["scenario"]
            failures = defaultdict(list)
            for failure in scenario["failures"]:
                failures[failure["case"]].append(failure)
            counts = Counter()
            for line in (root / "contract" / "recordings" / (name + ".jsonl")).read_text().splitlines():
                record = json.loads(line)
                if "request" not in record:
                    continue
                counts["cases"] += 1
                pending, registered = [], False
                for failure in failures[record["id"]]:
                    if global_tolerance(failure, record["response"]["status"]):
                        counts["globally_tolerated_fields"] += 1
                        continue
                    matches = covering(entries, failure)
                    if matches and numeric_change(failure) and not durable_counter(failure, matches):
                        numeric_rejections.append({"scenario": name, "case": record["id"], "path": failure["path"]})
                        matches = []
                    if matches:
                        registered = True
                        counts["registered_fields"] += 1
                        hits.update([matches[0]["id"]])
                    else:
                        pending.append(failure)
                if pending:
                    counts["failed_cases"] += 1
                    unresolved.extend({"scenario": name, "case": record["id"], "route": failure["route"],
                                       "category": failure["category"], "path": failure["path"]} for failure in pending)
                else:
                    counts["passed_cases"] += 1
                    counts["waived_cases"] += int(registered)
            scenarios.append({"scenario": name, **dict(counts), "raw_failing_fields": len(scenario["failures"]),
                              "raw_report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    totals = Counter()
    for scenario in scenarios:
        totals.update({key: value for key, value in scenario.items() if isinstance(value, int)})
    return {
        "kind": "read-only policy diagnostic, not an external conductor execution",
        "mode": "semantic",
        "policy": "W3 gateway prompt: global free error wording and Vary; exact registers; numeric changes refused except exact F-18 durable counters",
        "threshold": "board only",
        "totals": dict(totals),
        "scenarios": scenarios,
        "register_field_hits": dict(hits),
        "remaining_fields": unresolved,
        "rejected_numeric_register_matches": numeric_rejections,
        "note": "No comparator, recording, threshold or raw failure was edited. Missing numerical facts and genuine authorization changes remain unresolved.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = diagnostic(Path(__file__).resolve().parents[2], args.raw)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"totals": report["totals"], "scenarios": report["scenarios"],
                      "numeric_register_matches_rejected": len(report["rejected_numeric_register_matches"])}, indent=2))


if __name__ == "__main__":
    main()
