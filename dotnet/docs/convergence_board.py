"""Policy diagnostics over unchanged semantic replay reports; never alters replay comparisons."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

THRESHOLDS = {"framework": 90, "reads_calc": 95, "claims_artifacts_rules": 90, "drafts_runs": 90, "ai": 90}


def matches(template: str, operation: str) -> bool:
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", pattern)
    return re.fullmatch(pattern, operation) is not None


def group_for(groups: dict, operation: str, scenario: str) -> str:
    candidates = [(template.count("{"), name) for name, routes in groups.items()
                  for template in routes if matches(template, operation)]
    return min(candidates)[1] if candidates else "_unassigned"


def tolerated(failure: dict, status: int) -> bool:
    path = failure["path"]
    if path == "headers.vary":
        return True
    if re.match(r"^detail\[\d+\]\.(msg|input|ctx)(?:[.\[]|$)", path):
        return True
    if re.search(r"(?:^|\.)findings\[\d+\]\.message$", path):
        return True
    return status >= 400 and failure["category"] == "value" and path in ("detail", "detail.message", "detail.reason")


def numeric_change(failure: dict) -> bool:
    if failure["category"] != "value":
        return False
    before = re.findall(r"\d+(?:\.\d+)?", str(failure.get("expected", "")))
    after = re.findall(r"\d+(?:\.\d+)?", str(failure.get("actual", "")))
    return bool(before and after and before != after)


def covering(entries: list[dict], failure: dict) -> list[dict]:
    return [entry for entry in entries if matches(entry["route"], failure["route"])
            and (not entry.get("case") or entry["case"] in (failure["case"], failure["scenario"] + ":" + failure["case"]))
            and (not entry.get("categories") or failure["category"] in entry["categories"])
            and (not entry.get("path_prefix") or failure["path"].startswith(entry["path_prefix"]))]


def summarize(root: Path, raw: Path) -> dict:
    groups = json.loads((root / "dotnet/docs/route-groups.json").read_text())["groups"]
    entries = [entry for path in sorted((root / "dotnet/docs/improvements").glob("*.json"))
               for entry in json.loads(path.read_text(encoding="utf-8-sig")).get("improvements", [])]
    counts, clusters = defaultdict(Counter), defaultdict(Counter)
    remaining, rejected = [], []
    for path in sorted(raw.glob("*.json")):
        for scenario in json.loads(path.read_text())["scenarios"]:
            name = scenario["scenario"]
            failures = defaultdict(list)
            for failure in scenario["failures"]:
                failures[failure["case"]].append(failure)
            for line in (root / "contract/recordings" / (name + ".jsonl")).read_text().splitlines():
                record = json.loads(line)
                if "request" not in record:
                    continue
                operation = record["request"]["method"] + " " + record["request"]["path"]
                group = group_for(groups, operation, name)
                count = counts[group]
                count["cases"] += 1
                unresolved, waived = [], []
                for failure in failures[record["id"]]:
                    if tolerated(failure, record["response"]["status"]):
                        count["tolerated_fields"] += 1
                        continue
                    covers = covering(entries, failure)
                    if covers and numeric_change(failure):
                        rejected.append({**failure, "registers": [entry["id"] for entry in covers]})
                    if covers and not numeric_change(failure):
                        waived.append(failure)
                    else:
                        unresolved.append(failure)
                if unresolved:
                    count["failed"] += 1
                    remaining.extend({**failure, "group": group} for failure in unresolved)
                    for failure in unresolved:
                        key = failure["category"] + " " + re.sub(r"\[\d+\]", "[]", failure["path"])
                        clusters[group][key] += 1
                else:
                    count["passed"] += 1
                    if waived:
                        count["waived"] += 1
    board = {}
    for group, count in sorted(counts.items()):
        percentage = 100 * count["passed"] / count["cases"]
        board[group] = {**count, "pass_percent": round(percentage, 2),
                        "waived_percent": round(100 * count["waived"] / count["cases"], 2)}
        if group in THRESHOLDS:
            board[group]["threshold"] = THRESHOLDS[group]
            board[group]["threshold_met"] = percentage >= THRESHOLDS[group]
            board[group]["waiver_limit_met"] = count["waived"] / count["cases"] <= 0.25
    return {"mode": "semantic", "groups": board, "remaining_fields": remaining,
            "rejected_numeric_waivers": rejected,
            "clusters": {group: dict(count.most_common()) for group, count in clusters.items()},
            "note": "Policy diagnostic, not a replacement for the conductor. Raw reports are unchanged. Waiver shares are shown, never hidden."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    board = summarize(Path(__file__).resolve().parents[2], args.raw)
    args.out.write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(board["groups"], indent=2))
    print("Rejected numeric waiver matches:", len(board["rejected_numeric_waivers"]))
    return 0 if not board["rejected_numeric_waivers"] and all(
        board["groups"].get(group, {}).get("threshold_met", False)
        and board["groups"][group]["waiver_limit_met"] for group in THRESHOLDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
