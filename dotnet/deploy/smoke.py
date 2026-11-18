"""Exercise ordinary publications using only synthetic local stores and loopback HTTP."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from stage import DEPLOY, SERVICES

HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SYNTHETIC_TENANT = "00000000-0000-0000-0000-000000000001"


def environment(service: str, package: Path, work: Path) -> dict[str, str]:
    # Do not inherit credentials, proxy settings, model settings or customer bindings.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "DOTNET_ROOT", "COMSPEC"}
    result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result.update({
        "ENVIRONMENT": "local", "DATA_CLASSIFICATION": "synthetic",
        "REPOSITORY_ROOT": str(package / "resources"), "CONTRACT_HOOKS": "0",
        "PERSISTENCE_PROVIDER": "sqlite", "OPERATIONAL_DB": str(work / "ops.db"),
        "ARTIFACT_STORE": "local", "ARTIFACT_LOCAL_ROOT": str(work / "bytes"),
        "DATA_SOURCE": "csv", "PAYROLL_PATH": str(work / "absent-synthetic.csv"),
        "AUTH_MODE": "entra", "AUTH_TENANT_ID": SYNTHETIC_TENANT,
        "TENANT_ID": SYNTHETIC_TENANT, "API_AUDIENCE": "api://synthetic-api",
        "GATEWAY_AUDIENCE": "api://synthetic-gateway", "CLIENT_ALLOWLIST": "{}",
        "CHANNEL_DEBUG_WHOAMI": "false", "Logging__LogLevel__Default": "None",
        "ASPNETCORE_ENVIRONMENT": "Production", "DOTNET_NOLOGO": "1",
    })
    if service == "orchestrator":
        result.update({
            "CHANNEL_GATEWAY_URL": "https://gateway.example.test",
            "CHANNEL_GATEWAY_AUDIENCE": "api://synthetic-gateway",
            "AI_PROVIDER_CHAIN": "gateway", "AI_GATEWAY_ENDPOINT": "https://model.example.test",
            "AI_GATEWAY_AUTH": "none", "AI_GATEWAY_TLS_VERIFY": "true",
            "AI_MODEL_ROUTER": "synthetic", "AI_MODEL_NARRATOR": "synthetic",
            "AI_MODEL_ANALYSIS": "synthetic", "AI_EGRESS_POLICY": "block",
            "AI_INJECTION_GUARD": "on", "AI_OUTPUT_POLICY": "on",
            "KNOWLEDGE_ENABLED": "false", "KNOWLEDGE_PROVIDER": "none",
        })
    return result


def request(port: int, path: str, method: str = "GET") -> tuple[int, bytes]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    try:
        with HTTP.open(req, timeout=2) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def wait(port: int, path: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Synthetic host exited before health: code {process.returncode}.")
        try:
            if request(port, path)[0] == 200:
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Synthetic host did not become live before its deadline.")


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def verify_resources(package: Path, needs_resources: bool) -> int:
    manifest = json.loads((package / "artifact-manifest.json").read_text())
    import hashlib
    for item in manifest["files"]:
        actual = hashlib.sha256((package / item["path"]).read_bytes()).hexdigest()
        if actual != item["sha256"]:
            raise AssertionError("Published artifact checksum mismatch.")
    if needs_resources:
        assert (package / "resources" / "backend" / "rules").is_dir()
        assert (package / "resources" / "docs" / "data" / "schema" / "migrations").is_dir()
        assert not (package / "resources" / "contract").exists()
    return len(manifest["files"])


def smoke(service: str, package: Path) -> dict:
    if service == "orchestrator":
        from container_smoke import orchestrator
        return orchestrator(package)
    checks = {"hashed_files": verify_resources(package, service != "orchestrator")}
    temp_root = DEPLOY / ".artifacts" / "smoke"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=service + "-", dir=temp_root) as directory:
        work = Path(directory)
        env = environment(service, package, work)
        command = ["dotnet", str(package / ("TaxCredit." + SERVICES[service] + ".dll"))]
        if service == "worker":
            completed = subprocess.run(command + ["--once"], cwd=work, env=env,
                                       capture_output=True, timeout=40)
            assert completed.returncode == 0, "Finite Worker failed."
            assert b"Processed 0 queue items." in completed.stdout, "Worker progress was not observed."
            checks.update({"once_exit": 0, "processed_observed": 0, "http_listener": False})
            env["ENVIRONMENT"] = "azure"
            refused = subprocess.run(command + ["--once"], cwd=work, env=env,
                                     capture_output=True, timeout=40)
            assert refused.returncode != 0, "Deployed local-store Worker must be refused."
            checks["invalid_deployed_local_store_refused"] = True
            return checks
        port = free_port()
        command += ["--urls", f"http://127.0.0.1:{port}"]
        process = subprocess.Popen(command, cwd=work, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            health = "/api/health"
            wait(port, health, process)
            checks["liveness_status"] = 200
            if service == "api":
                status, body = request(port, "/api/ready")
                assert status == 200 and json.loads(body)["ready"] is False
                checks["unavailable_readiness_status"] = status
                checks["unavailable_readiness_body"] = False
                protected = "/api/scope"
            elif service == "gateway":
                status, body = request(port, "/channel/ready")
                assert status == 200 and json.loads(body)["ready"] is True
                checks["static_readiness_false_positive_observed"] = True
                assert request(port, "/api/ready")[0] == 404
                protected = "/channel/v1/tools"
            assert request(port, protected)[0] == 401
            assert request(port, "/__contract__/reset", "POST")[0] == 404
            checks.update({"unauthorized_status": 401, "contract_controls_status": 404})
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=20)
        checks["ordinary_process_stopped"] = True
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEPLOY / ".artifacts" / "published-smoke.json")
    parser.add_argument("--service", choices=[*SERVICES, "all"], default="all")
    args = parser.parse_args()
    result = {"kind": "synthetic-publication-only", "services": {}}
    for name in SERVICES if args.service == "all" else [args.service]:
        result["services"][name] = smoke(name, DEPLOY / ".artifacts" / "publish" / name)
        print(f"{name}: ordinary synthetic checks passed.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
