"""Reproduce the package/reset lifecycle on an exclusively owned ordinary host."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    oracle = os.environ.get("CONTRACT_PYTHON", r"C:\Projects\py312-oracle\.venv\Scripts\python.exe")
    evidence = {}
    with tempfile.TemporaryDirectory(prefix="claims-reset-probe-", dir=root / "dotnet" / "artifacts") as directory:
        work = Path(directory)
        env = {
            **os.environ, "CONTRACT_HOOKS": "1", "ENVIRONMENT": "local",
            "AUTH_MODE": "none", "DATA_SOURCE": "csv", "REPOSITORY_ROOT": str(root),
            "OPERATIONAL_DB": str(work / "operations.db"), "ARTIFACT_LOCAL_ROOT": str(work / "bytes"),
            "FOUNDRY_PROJECT_ENDPOINT": "", "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
            "Logging__LogLevel__Default": "Warning",
            "Logging__LogLevel__Microsoft.Hosting.Lifetime": "Information",
            "PYTHONPATH": str(root), "PYTHONUTF8": "1",
        }
        with (work / "host.log").open("w", encoding="utf-8") as log:
            host = subprocess.Popen(
                ["dotnet", str(root / "dotnet" / "artifacts" / "bin" / "TaxCredit.Api" / "debug" / "TaxCredit.Api.dll"),
                 "--urls", "http://127.0.0.1:0"],
                cwd=root / "dotnet", env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 60
                url = None
                while time.monotonic() < deadline:
                    found = re.search(r"Now listening on: (http://127\.0\.0\.1:\d+)",
                                      (work / "host.log").read_text(encoding="utf-8"))
                    if found:
                        url = found[1]
                        break
                    if host.poll() is not None:
                        raise RuntimeError("Owned host exited before readiness")
                    time.sleep(.2)
                if url is None:
                    raise TimeoutError("Owned host did not become ready")

                def call(path, body=None):
                    request = urllib.request.Request(
                        url + path, data=None if body is None else json.dumps(body).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    try:
                        with urllib.request.urlopen(request, timeout=120) as response:
                            response.read()
                            return response.status
                    except urllib.error.HTTPError as error:
                        error.read()
                        return error.code

                evidence["health"] = call("/api/health")
                evidence["initial_reset"] = call("/__contract__/reset", {})
                evidence["reset_without_artifact"] = call("/__contract__/reset", {})
                evidence["create_package"] = call("/api/clients/1001/packages?tax_year=2023", {})
                evidence["reset_after_package"] = call("/__contract__/reset", {})
                result = subprocess.run(
                    [oracle, "-m", "contract.replay", "--mode", "semantic", "--base-url", url,
                     "--reset-url", url + "/__contract__/reset", "--scenario", "p1_reads",
                     "--out", str(work / "replay")],
                    cwd=root / "backend", env=env, capture_output=True, text=True, encoding="utf-8",
                )
                evidence["conductor_style_replay_exit"] = result.returncode
                evidence["conductor_style_replay_report_exists"] = (work / "replay.json").exists()
                evidence["conductor_style_replay_error"] = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else None
                if (work / "replay.json").exists():
                    report = json.loads((work / "replay.json").read_text(encoding="utf-8"))
                    evidence["replay_exchanges"] = report["exchanges"]
                    evidence["replay_failures"] = report["failure_count"]
            finally:
                host.terminate()
                try:
                    host.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    host.kill()
                    host.wait(timeout=15)
    args.out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if all(evidence[key] == expected for key, expected in {
        "health": 200, "initial_reset": 200, "reset_without_artifact": 200,
        "create_package": 201, "reset_after_package": 200,
        "conductor_style_replay_report_exists": True,
    }.items()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
