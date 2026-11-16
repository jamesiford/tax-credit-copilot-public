"""Run the unchanged replay and summarize case-level results without recording payloads."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


def classify(root: Path, request: dict, scenario: str) -> str:
    if scenario.startswith("g1_"):
        return "gateway"
    groups = json.loads((root / "dotnet/docs/route-groups.json").read_text())
    path = request["path"].rstrip("/")
    candidates = []
    for name, routes in groups["groups"].items():
        for operation in routes:
            method, template = operation.split(" ", 1)
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", template)
            if re.fullmatch(pattern, path, re.IGNORECASE):
                candidates.append((template.count("{"), method != request["method"], name))
    return min(candidates)[2] if candidates else "framework"


def summarize(root: Path, reports: list[dict]) -> dict:
    counts = defaultdict(Counter)
    categories = defaultdict(Counter)
    for report in reports:
        for scenario in report["scenarios"]:
            failed = {failure["case"] for failure in scenario["failures"]}
            for line in (root / "contract/recordings" / (scenario["scenario"] + ".jsonl")).read_text().splitlines():
                record = json.loads(line)
                group = classify(root, record.get("request", {}), scenario["scenario"]) if "request" in record else "control"
                counts[group]["cases"] += 1
                counts[group]["failed" if record["id"] in failed else "passed"] += 1
            for failure in scenario["failures"]:
                categories[scenario["scenario"]][failure["category"]] += 1
    return {
        "mode": "semantic",
        "groups": {group: {
            "cases": count["cases"], "passed": count["passed"], "failed": count["failed"],
            "pass_percent": round(100 * count["passed"] / count["cases"], 2),
            "status": "green" if count["passed"] / count["cases"] >= (0.5 if group == "framework" else 1) else "red",
        }
                   for group, count in sorted(counts.items())},
        "failure_categories": dict(categories),
        "waived_cases": 0,
        "note": "Raw replay results, no waivers. Deferred business and gateway groups are red by design.",
    }


def run_scenario(root: Path, oracle: str, env: dict, base_url: str, scenario_file: Path, raw: Path) -> dict:
    scenario = json.loads(scenario_file.read_text())
    output = raw.resolve() / scenario_file.stem
    report_file = output.with_suffix(".json")
    report_file.unlink(missing_ok=True)
    result = subprocess.run([
        oracle, "-m", "contract.replay", "--mode", "semantic",
        "--base-url", base_url,
        "--reset-url", base_url + "/__contract__/reset?profile=" + scenario["profile"],
        "--scenario", scenario_file.stem, "--out", str(output),
    ], cwd=root / "backend", env=env, check=False)
    if result.returncode not in (0, 1) or not report_file.exists():
        raise RuntimeError(f"Replay did not produce a report: {scenario_file.stem}")
    return json.loads(report_file.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--group", help="Select the displayed group; prerequisite exchanges are still replayed.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--raw-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    oracle = os.environ.get("CONTRACT_PYTHON", r"C:\Projects\py312-oracle\.venv\Scripts\python.exe")
    env = {**os.environ, "PYTHONPATH": str(root), "CONTRACT_PYTHON": oracle, "PYTHONUTF8": "1"}
    raw = Path(args.raw_dir).resolve()
    raw.mkdir(parents=True, exist_ok=True)
    reports = []
    for scenario_file in sorted((root / "contract/scenarios").glob("*.json")):
        if args.scenario and scenario_file.stem not in args.scenario:
            continue
        reports.append(run_scenario(root, oracle, env, args.base_url, scenario_file, raw))
    board = summarize(root, reports)
    if args.group and args.group not in board["groups"]:
        raise ValueError(f"No exchanges found for group: {args.group}")
    Path(args.out).write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    selected = {args.group: board["groups"][args.group]} if args.group else board["groups"]
    print(json.dumps(selected, indent=2))
    target = args.group or "framework"
    return 0 if board["groups"].get(target, {}).get("status") == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
