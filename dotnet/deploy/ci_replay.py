"""Reuse public replay and policy scoring; persist aggregates only and never waive a new difference."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from stage import DEPLOY, ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True, choices=["api", "gateway"])
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("The replay oracle must be CPython 3.12.")
    scenarios = [path.stem for path in sorted((ROOT / "contract" / "scenarios").glob("*.json"))
                 if path.stem.startswith("g1_") == (args.group == "gateway")]
    output_parent = ROOT / "dotnet" / "artifacts"
    output_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="deploy-replay-" + args.group + "-", dir=output_parent))
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "DOTNET_ROOT", "COMSPEC"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update({"CONTRACT_PYTHON": sys.executable, "PYTHONUTF8": "1",
                        "PYTHONDONTWRITEBYTECODE": "1", "DOTNET_NOLOGO": "1",
                        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1"})
    command = [sys.executable, str(ROOT / "dotnet" / "docs" / "run_wave_replays.py"), "--out", str(work)]
    for scenario in scenarios:
        command += ["--scenario", scenario]
    try:
        subprocess.run(command, cwd=ROOT / "dotnet", env=environment, check=True)
        sys.path.insert(0, str(ROOT / "dotnet" / "docs"))
        from wave_replay_report import summarize
        report = summarize(ROOT, [work / args.group / "replay.json"])
        groups = report["groups"]
        passed = all(group.get("threshold_met", True) and group["waiver_share_at_most_25_percent"]
                     for group in groups.values())
        safe = {"kind": "existing-semantic-policy", "host": args.group, "groups": groups,
                "policy_pass": passed,
                "exchanges": sum(source["exchanges"] for source in report["sources"]),
                "raw_differing_fields": sum(source["raw_fields"] for source in report["sources"])}
        destination = DEPLOY / ".artifacts" / ("ci-replay-" + args.group + ".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
        print(f"{args.group}: existing policy {'passed' if passed else 'blocked'}; only aggregates retained.")
    finally:
        shutil.rmtree(work)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
