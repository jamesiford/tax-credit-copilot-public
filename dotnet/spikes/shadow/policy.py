"""Current injected scoring, separately projected over unchanged synthetic replay diffs."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

from admission import ROOT
from safe_compare import safe_path

sys.path.insert(0, str(ROOT / "dotnet" / "docs"))
from convergence_board import covering, group_for, matches, numeric_change  # noqa: E402
from wave_replay_report import accepted_entries  # noqa: E402

THRESHOLDS = {"framework": 90, "reads_calc": 95, "claims_artifacts_rules": 90,
              "drafts_runs": 90, "ai": 90, "gateway": 90}
VALUE_PATHS = (r"^detail$", r"^detail\.(reason|remedy|message)$", r"^error\.message$",
               r"^result\.structuredContent\.error\.message$")
FREE_PATHS = (r"^detail\[\d+\]\.(msg|ctx|input|url)$", r"^headers\.vary$",
              r"(^|\.)validation\.findings\[\d+\]\.message$")


def global_tolerance(failure: dict) -> bool:
    if failure["category"] == "status":
        return False
    path = failure["path"]
    if any(re.search(pattern, path) for pattern in FREE_PATHS):
        return True
    return failure["category"] == "value" and (
        any(re.search(pattern, path) for pattern in VALUE_PATHS)
        or bool(re.fullmatch(r"result\.content\[\d+\]\.text", path)
                and re.match(r"^The request did not go through", str(failure.get("expected", "")))))


def exact_numeric_entries(failure: dict, record: dict, entries: list[dict]) -> list[dict]:
    accepted = accepted_entries(failure, record, entries)
    if not numeric_change(failure) or failure["path"] == "body.text":
        return accepted
    return [entry for entry in accepted if entry.get("finding") == "F-18"
            and entry.get("path_prefix") == failure["path"]
            and re.search(r"(^|\.)(preview|dry_run_summary)\.(never_run|skip_coverage|skip_candidates_upper_bound)$",
                          failure["path"])]


def template_for(groups: dict, route: str) -> str:
    candidates = [template for routes in groups.values() for template in routes if matches(template, route)]
    return min(candidates, key=lambda value: value.count("{")) if candidates else route.split(" ", 1)[0] + " {unassigned}"


def summarize(files: list[Path]) -> dict:
    groups = json.loads((ROOT / "dotnet" / "docs" / "route-groups.json").read_text())["groups"]
    entries = [entry for path in sorted((ROOT / "dotnet" / "docs" / "improvements").glob("*.json"))
               for entry in json.loads(path.read_text(encoding="utf-8-sig"))["improvements"]]
    counts, matches_all, hits = defaultdict(Counter), Counter(), Counter()
    residuals, sources, scenarios, controls = [], [], set(), Counter()
    for path in files:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["mode"] != "semantic":
            raise ValueError("semantic-reports-only")
        sources.append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "steps": report["exchanges"], "raw_fields": report["failure_count"]})
        for scenario in report["scenarios"]:
            name = scenario["scenario"]
            if name in scenarios:
                raise ValueError("duplicate-scenario")
            scenarios.add(name)
            failures, semantic = defaultdict(list), defaultdict(list)
            for failure in scenario["failures"]:
                failures[failure["case"]].append(failure)
            for tolerated in scenario["tolerated"]:
                semantic[tolerated["case"]].append(tolerated)
            records = [json.loads(line) for line in (ROOT / "contract" / "recordings" / (name + ".jsonl"))
                       .read_text(encoding="utf-8").splitlines()]
            if len(records) != scenario["exchanges"]:
                raise ValueError("record-denominator")
            known_cases = {record["id"] for record in records}
            if set(failures) - known_cases:
                raise ValueError("unscored-scenario-or-control-failure")
            for record in records:
                if "request" not in record:
                    controls["steps"] += 1
                    controls["raw_fields"] += len(failures[record["id"]])
                    controls["failed"] += int(bool(failures[record["id"]]))
                    continue
                route = record["request"]["method"] + " " + record["request"]["path"]
                group = "gateway" if name.startswith("g1_") else group_for(groups, route, name)
                count, unresolved, registered = counts[group], [], False
                count["http"] += 1
                count["raw_fields"] += len(failures[record["id"]])
                count["raw_failed_cases"] += int(bool(failures[record["id"]]))
                count["semantic_tolerance_fields"] += len(semantic[record["id"]])
                for ordinal, failure in enumerate(failures[record["id"]], 1):
                    matches_all.update({entry["id"] for entry in covering(entries, failure)})
                    if global_tolerance(failure):
                        count["global_fields"] += 1
                        continue
                    accepted = exact_numeric_entries(failure, record, entries)
                    if accepted:
                        registered = True
                        count["registered_fields"] += 1
                        hits.update([accepted[0]["id"]])
                    else:
                        unresolved.append(failure)
                        residuals.append({"scenario": name, "case": record["id"], "group": group,
                                          "route": template_for(groups, route), "path_template": safe_path(failure["path"]),
                                          "category": failure["category"], "field_ordinal": ordinal})
                count["registered_dependent_cases"] += int(registered)
                count["failed"] += int(bool(unresolved))
                count["unresolved_fields"] += len(unresolved)
                count["passed"] += int(not unresolved)
                count["waived_passed_cases"] += int(registered and not unresolved)
    board = {}
    for group, count in sorted(counts.items()):
        item = {key: count[key] for key in ("http", "raw_fields", "raw_failed_cases", "semantic_tolerance_fields",
                "global_fields", "registered_fields", "registered_dependent_cases", "failed", "unresolved_fields",
                "passed", "waived_passed_cases")}
        item["pass_percent"] = round(100 * count["passed"] / count["http"], 2)
        item["waived_percent"] = round(100 * count["waived_passed_cases"] / count["http"], 2)
        item["cap_exempt_below_40"] = count["http"] < 40
        item["cap_met"] = item["cap_exempt_below_40"] or item["waived_percent"] <= 25
        if group in THRESHOLDS:
            item["required_percent"] = THRESHOLDS[group]
            item["threshold_met"] = item["pass_percent"] >= THRESHOLDS[group]
        board[group] = item
    return {"kind": "W4 current-policy projection; not an external conductor run or cutover approval",
            "product_revision": "006760b", "classification": "isolated synthetic",
            "sources": sources, "scenario_count": len(scenarios), "groups": board, "controls": dict(controls),
            "register_match_fields": dict(matches_all), "register_accepted_fields": dict(hits),
            "unresolved": residuals, "policy": {"cap_min_exchanges": 40, "max_waived_percent": 25,
                "recorded_list_semantics": True, "value_paths": VALUE_PATHS, "free_paths": FREE_PATHS,
                "numeric_exception": "exact registered F-18 paths only; no calculated values"}}


if __name__ == "__main__":
    files = [ROOT / "dotnet" / "artifacts" / "w4-integration" / "baseline" / kind / "replay.json"
             for kind in ("api", "gateway")]
    report = summarize(files)
    target = ROOT / "dotnet" / "docs" / "integration-replay.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"groups": report["groups"], "controls": report["controls"]}, indent=2))
