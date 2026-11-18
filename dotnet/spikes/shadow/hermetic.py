"""Ordinary local hosts with a fresh synthetic store; never accepts a remote target."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from admission import ORACLE, ROOT

OS_KEYS = frozenset(("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA",
                     "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "DOTNET_ROOT",
                     "NUGET_PACKAGES", "DOTNET_CLI_HOME", "HOMEDRIVE", "HOMEPATH", "PATHEXT", "COMSPEC",
                     "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"))
HOSTS = {"api": "TaxCredit.Api", "gateway": "TaxCredit.Gateway", "python": None}


def environment(output: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if key.upper() in OS_KEYS}
    temporary = output / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env.update({"PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
                "CONTRACT_PYTHON": str(ORACLE), "ORACLE_PYTHON": str(ORACLE),
                "ENVIRONMENT": "local", "DATA_CLASSIFICATION": "synthetic", "DATA_SOURCE": "csv",
                "PERSISTENCE_PROVIDER": "sqlite", "ARTIFACT_STORE": "local", "AUTH_MODE": "none",
                "CONTRACT_HOOKS": "1", "CONTRACT_DIR": str(ROOT / "contract"),
                "REPOSITORY_ROOT": str(ROOT), "SEED_ROOT": str(ROOT / "contract" / "seed"),
                "OPERATIONAL_DB": str(output / "operations.db"), "ARTIFACT_LOCAL_ROOT": str(output / "bytes"),
                "FOUNDRY_PROJECT_ENDPOINT": "", "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
                "OTEL_SDK_DISABLED": "true", "WARM_ON_START": "0", "RUN_WORKER_INLINE": "0"})
    env.update({key: str(temporary) for key in ("TEMP", "TMP", "TMPDIR")})
    return env


def artifact_directory(name: str) -> Path:
    if name not in ("baseline", "paired", "cross-surface"):
        raise ValueError("closed-output-name")
    output = ROOT / "dotnet" / "artifacts" / "w4-integration" / name
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("Fresh synthetic evidence requires an empty output directory.")
    return output


def _wait(process, url: str) -> None:
    deadline = time.monotonic() + 120
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Isolated host exited before readiness.")
        try:
            with client.open(url + "/api/health", timeout=1) as reply:
                if reply.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError("Isolated host readiness deadline.")


@contextmanager
def host(kind: str, output: Path, profile: str = "P1"):
    if kind not in HOSTS or profile not in ("P1", "G1"):
        raise ValueError("closed-host-or-profile")
    output.mkdir(parents=True, exist_ok=True)
    env = environment(output)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    if kind == "python":
        command = [str(ORACLE), "-m", "contract.harness.server", "--profile", profile, "--port", str(port)]
    else:
        binary = ROOT / "dotnet" / "artifacts" / "bin" / HOSTS[kind] / "release" / (HOSTS[kind] + ".dll")
        if not binary.is_file():
            raise FileNotFoundError("Build the Release hosts before observation.")
        command = ["dotnet", str(binary), "--urls", url]
    # Only hermetic processes may produce raw logs. No live URL can enter this launcher.
    with (output / "host.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT / "dotnet", env=env, stdout=log, stderr=log)
        try:
            _wait(process, url)
            yield url, env
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def replay_baseline() -> dict:
    output = artifact_directory("baseline")
    results = {}
    for kind in ("api", "gateway"):
        local = output / kind
        with host(kind, local) as (url, env):
            names = [path.stem for path in sorted((ROOT / "contract" / "scenarios").glob("*.json"))
                     if path.stem.startswith("g1_") == (kind == "gateway")]
            target = local / "replay"
            args = [str(ORACLE), "-m", "contract.replay", "--mode", "semantic", "--base-url", url,
                    "--reset-url", url + "/__contract__/reset", "--out", str(target.resolve())]
            for name in names:
                args.extend(["--scenario", name])
            with (local / "replay.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(args, cwd=ROOT / "backend", env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=1800, check=False)
            report_path = target.with_suffix(".json")
            if result.returncode not in (0, 1) or not report_path.is_file():
                raise RuntimeError("Isolated replay did not complete.")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            results[kind] = {"steps": report["exchanges"], "raw_fields": report["failure_count"],
                             "scenarios": len(report["scenarios"]), "runner_exit": result.returncode}
            print(kind, json.dumps(results[kind]), flush=True)
    return results


if __name__ == "__main__":
    if sys.argv[1:] != ["--baseline"]:
        raise SystemExit("Use --baseline; targets are closed and local-only.")
    replay_baseline()
