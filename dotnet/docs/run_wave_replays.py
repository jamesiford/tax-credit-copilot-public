"""Launch both ordinary hosts and run the public replay with no manual setup."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request


def wait_ready(process: subprocess.Popen, url: str) -> None:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Replay host exited with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise TimeoutError("Replay host did not become ready.")


def run_host(root: Path, output: Path, host: str, selected: list[str]) -> None:
    gateway = host == "TaxCredit.Gateway"
    name = "gateway" if gateway else "api"
    scenarios = [path.stem for path in sorted((root / "contract" / "scenarios").glob("*.json"))
                 if path.stem.startswith("g1_") == gateway and (not selected or path.stem in selected)]
    if not scenarios:
        return
    local = output / name
    local.mkdir(parents=True, exist_ok=True)
    oracle = os.environ.get("CONTRACT_PYTHON", r"C:\Projects\py312-oracle\.venv\Scripts\python.exe")
    environment = {**os.environ, "PYTHONPATH": str(root), "CONTRACT_PYTHON": oracle,
                   "PYTHONUTF8": "1", "CONTRACT_DIR": str(root / "contract"),
                   "ENVIRONMENT": "local", "DATA_SOURCE": "csv",
                   "PERSISTENCE_PROVIDER": "sqlite", "ARTIFACT_STORE": "local",
                   "FOUNDRY_PROJECT_ENDPOINT": "", "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
                   "OPERATIONAL_DB": str(local / "operations.db"),
                   "ARTIFACT_LOCAL_ROOT": str(local / "bytes")}
    subprocess.run([oracle, "-c", "from contract.oracle import require; require(False)"],
                   cwd=root / "backend", env=environment, check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    command = ["dotnet", "run", "--no-build", "--no-launch-profile", "--project",
               str(root / "dotnet" / "src" / host), "--", "--urls", url]
    with (local / "host.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=log)
        try:
            wait_ready(process, url)
            arguments = [oracle, "-m", "contract.replay", "--mode", "semantic", "--base-url", url,
                         "--reset-url", url + "/__contract__/reset", "--out", str(local / "replay")]
            for scenario in scenarios:
                arguments.extend(["--scenario", scenario])
            report_path = local / "replay.json"
            report_path.unlink(missing_ok=True)
            with (local / "replay.log").open("w", encoding="utf-8") as replay_log:
                result = subprocess.run(arguments, cwd=root / "backend", env=environment,
                                        stdout=replay_log, stderr=subprocess.STDOUT, check=False)
            if result.returncode not in (0, 1) or not report_path.exists():
                raise RuntimeError(f"{name} replay did not complete; inspect its replay.log.")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"{name}: {report['exchanges']} exchanges, {report['failure_count']} raw differing fields.", flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario", action="append", default=[])
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = arguments.out.resolve()
    if not output.is_relative_to(root / "dotnet" / "artifacts"):
        parser.error("--out must be beneath this worktree's dotnet/artifacts directory")
    for host in ("TaxCredit.Api", "TaxCredit.Gateway"):
        run_host(root, output, host, arguments.scenario)


if __name__ == "__main__":
    main()
