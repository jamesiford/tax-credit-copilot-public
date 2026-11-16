"""Replay complete scenarios against separate ordinary hosts, without sharing ports or state."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import urllib.request


def host_lines(stream, lines: queue.Queue[str]) -> None:
    for line in stream:
        lines.put(line)


def run(root: Path, scenario: str, output: Path, oracle: str) -> dict:
    work = output / "state" / scenario
    work.mkdir(parents=True, exist_ok=False)
    env = {
        **os.environ,
        "TCC_CONTRACT_HOOKS": "1",
        "ENVIRONMENT": "local",
        "AUTH_MODE": "none",
        "DATA_SOURCE": "csv",
        "TCC_REPOSITORY_ROOT": str(root),
        "OPERATIONAL_DB": str(work / "operations.db"),
        "ARTIFACT_LOCAL_ROOT": str(work / "bytes"),
        "Logging__LogLevel__Default": "Warning",
        "Logging__LogLevel__Microsoft.Hosting.Lifetime": "Information",
        "FOUNDRY_PROJECT_ENDPOINT": "",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
    }
    host = subprocess.Popen(
        ["dotnet", str(root / "dotnet/artifacts/bin/TaxCredit.Api/debug/TaxCredit.Api.dll"),
         "--urls", "http://127.0.0.1:0"],
        cwd=root / "dotnet", env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
    )
    try:
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=host_lines, args=(host.stdout, lines), daemon=True).start()
        deadline = time.monotonic() + 60
        url = None
        while time.monotonic() < deadline:
            if host.poll() is not None:
                raise RuntimeError(f"{scenario}: local host exited before readiness")
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                continue
            found = re.search(r"Now listening on: (http://127\.0\.0\.1:\d+)", line)
            if found:
                url = found[1]
                break
        if url is None:
            raise TimeoutError(f"{scenario}: local host did not become ready")
        with urllib.request.urlopen(url + "/api/health", timeout=15) as health:
            if health.status != 200:
                raise RuntimeError(f"{scenario}: local health refused")
        print(f"{scenario}: isolated host ready; replaying full scenario", flush=True)
        result = subprocess.run(
            [oracle, str(root / "dotnet/src/TaxCredit.Api/Contract/replay_board.py"),
             "--base-url", url, "--scenario", scenario, "--group", "claims_artifacts_rules",
             "--out", str(output / (scenario + "-board.json")),
             "--raw-dir", str(output / "raw")],
            cwd=root, env={**env, "CONTRACT_PYTHON": oracle}, check=False,
        )
        report = output / "raw" / (scenario + ".json")
        if result.returncode not in (0, 1) or not report.exists():
            raise RuntimeError(f"{scenario}: replay failed to produce evidence")
        return json.loads(report.read_text(encoding="utf-8"))
    finally:
        host.terminate()
        try:
            host.wait(timeout=15)
        except subprocess.TimeoutExpired:
            host.kill()
            host.wait(timeout=15)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scenario", action="append", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    oracle = os.environ.get("CONTRACT_PYTHON", r"C:\Projects\py312-oracle\.venv\Scripts\python.exe")
    spec = importlib.util.spec_from_file_location("board", root / "dotnet/src/TaxCredit.Api/Contract/replay_board.py")
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)
    reports = [run(root, scenario, output, oracle) for scenario in args.scenario]
    summary = board.summarize(root, reports)
    (output / "board.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["groups"]["claims_artifacts_rules"], indent=2))
    return 0 if summary["groups"]["claims_artifacts_rules"]["status"] == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
