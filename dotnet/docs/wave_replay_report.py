"""Audit dual-host raw replays under the W3 policy, without changing comparisons."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from convergence_board import THRESHOLDS, covering, group_for, numeric_change
from gateway_replay_report import durable_counter, global_tolerance


def registered_markup(failure: dict, record: dict, entries: list[dict]) -> bool:
    """Documentation HTML is a registered framework document, not a JSON figure."""
    return (failure["category"] == "value" and failure["path"] == "body.text"
            and failure["route"] in ("GET /docs", "GET /redoc", "GET /docs/oauth2-redirect")
            and record["response"]["body"]["kind"] == "text"
            and record["response"]["headers"].get("content-type", "").startswith("text/html")
            and any(entry["kind"] == "framework_default" for entry in entries))


def accepted_entries(failure: dict, record: dict, entries: list[dict]) -> list[dict]:
    matches = covering(entries, failure)
    if numeric_change(failure) and not (durable_counter(failure, matches)
                                       or registered_markup(failure, record, matches)):
        return []
    return matches


def summarize(root: Path, raw_files: list[Path]) -> dict:
    groups = json.loads((root / "dotnet" / "docs" / "route-groups.json").read_text())["groups"]
    entries = [entry for path in sorted((root / "dotnet" / "docs" / "improvements").glob("*.json"))
               for entry in json.loads(path.read_text(encoding="utf-8-sig")).get("improvements", [])]
    counts, clusters = defaultdict(Counter), defaultdict(Counter)
    remaining, sources, hits, seen = [], [], Counter(), set()
    for path in raw_files:
        report = json.loads(path.read_text(encoding="utf-8"))
        sources.append({"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "exchanges": report["exchanges"], "raw_fields": report["failure_count"]})
        if report["mode"] != "semantic":
            raise ValueError("A semantic raw report is required.")
        for scenario in report["scenarios"]:
            name = scenario["scenario"]
            if name in seen:
                raise ValueError(f"Duplicate scenario: {name}")
            seen.add(name)
            failures = defaultdict(list)
            for failure in scenario["failures"]:
                failures[failure["case"]].append(failure)
            for line in (root / "contract" / "recordings" / (name + ".jsonl")).read_text().splitlines():
                record = json.loads(line)
                if "request" not in record:
                    continue
                operation = record["request"]["method"] + " " + record["request"]["path"]
                group = "gateway" if name.startswith("g1_") else group_for(groups, operation, name)
                count, unresolved, waived = counts[group], [], False
                count["cases"] += 1
                for failure in failures[record["id"]]:
                    if global_tolerance(failure, record["response"]["status"]):
                        count["tolerated_fields"] += 1
                        continue
                    accepted = accepted_entries(failure, record, entries)
                    if accepted:
                        waived = True
                        count["registered_fields"] += 1
                        hits.update([accepted[0]["id"]])
                    else:
                        unresolved.append(failure)
                if unresolved:
                    count["failed"] += 1
                    remaining.extend({**failure, "group": group} for failure in unresolved)
                    for failure in unresolved:
                        cluster = failure["category"] + " " + re.sub(r"\[\d+\]", "[]", failure["path"])
                        clusters[group][cluster] += 1
                else:
                    count["passed"] += 1
                    count["waived"] += int(waived)
    thresholds = {**THRESHOLDS, "gateway": 90}
    board = {}
    for group, count in sorted(counts.items()):
        percentage = 100 * count["passed"] / count["cases"]
        board[group] = {**count, "pass_percent": round(percentage, 2),
                        "waived_percent": round(100 * count["waived"] / count["cases"], 2)}
        if group in thresholds:
            board[group]["required_percent"] = thresholds[group]
            board[group]["threshold_met"] = percentage >= thresholds[group]
        board[group]["waiver_share_at_most_25_percent"] = count["waived"] / count["cases"] <= 0.25
    return {
        "kind": "Local W3 policy audit; not an external conductor execution or a zero-difference replay",
        "sources": sources, "groups": board, "register_field_hits": dict(hits),
        "remaining_fields": remaining,
        "clusters": {group: dict(count.most_common()) for group, count in clusters.items()},
        "policy": [
            "Raw comparisons, recordings, group inventory and percentage thresholds remain unchanged.",
            "g1_ scenarios belong to the gateway host/group, including their health and documentation probes.",
            "Only existing documented global text tolerances and exact improvement entries apply.",
            "Numeric JSON differences are refused except exact registered F-18 operational preview counters.",
            "Existing registered native documentation HTML is a framework document, not a calculated JSON number.",
            "Waiver shares are separate from percentage thresholds; the inherited framework share is visible.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    report = summarize(root, [path.resolve() for path in args.raw])
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["groups"], indent=2))


if __name__ == "__main__":
    main()
