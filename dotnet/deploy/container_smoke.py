"""Observe real product containers in egress-disabled namespaces; retain only aggregate evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from smoke import environment, verify_resources
from stage import DEPLOY, SERVICES


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True, timeout=90)


class Container:
    def __init__(self, service: str, extra: dict | None = None, arguments: list | None = None,
                 network: str = "none", published: Path | None = None):
        env = environment(service, Path("/app"), Path("/tmp/tcc"))
        env = {key: value for key, value in env.items()
               if key.upper() not in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "DOTNET_ROOT"}}
        env.update({"REPOSITORY_ROOT": "/app/resources", "OPERATIONAL_DB": "/tmp/tcc/ops.db",
                    "ARTIFACT_LOCAL_ROOT": "/tmp/tcc/bytes", "PAYROLL_PATH": "/tmp/tcc/absent.csv"})
        env.update(extra or {})
        args = ["create", "--platform", "linux/amd64", "--network", network, "--ulimit", "core=0",
                "--tmpfs", "/tmp:rw,nosuid,size=128m", "--workdir", "/proof" if published else "/app"]
        if not published:
            args += ["--read-only"]
        for key, value in env.items():
            args += ["--env", f"{key}={value}"]
        if published:
            args += ["--entrypoint", "sh"]
        args += [f"tcc-w4-{service}:local"]
        args += ["/proof/start-orchestrator.sh"] if published else (arguments or [])
        self.id = docker(*args).stdout.strip()
        if published:
            try:
                docker("cp", str(published) + os.sep + ".", self.id + ":/proof")
            except subprocess.CalledProcessError:
                self.cleanup()
                raise

    def start(self) -> None:
        docker("start", self.id)

    def state(self) -> dict:
        return json.loads(docker("inspect", "--format", "{{json .State}}", self.id).stdout)

    def request(self, path: str, method: str = "GET") -> tuple[int, bytes]:
        response = docker("exec", self.id, "curl", "--silent", "--max-time", "3",
                          "--request", method, "--write-out", "\n%{http_code}",
                          "http://127.0.0.1:" + ("8088" if "readiness" in path else "8080") + path,
                          check=False)
        if response.returncode:
            return 0, b""
        body, status = response.stdout.rsplit("\n", 1)
        return int(status), body.encode()

    def wait(self, path: str) -> None:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if not self.state()["Running"]:
                raise RuntimeError(f"Synthetic container exited: {self.state()['ExitCode']}.")
            if self.request(path)[0] == 200:
                return
            time.sleep(0.25)
        raise RuntimeError("Synthetic container did not become live.")

    def stop(self) -> dict:
        started = time.monotonic()
        docker("stop", "--time", "15", self.id)
        state = self.state()
        assert state["ExitCode"] in {0, 143}, "Termination did not finish within the SIGTERM boundary."
        return {"sigterm_exit": state["ExitCode"], "stop_seconds": round(time.monotonic() - started, 3)}

    def cleanup(self) -> None:
        docker("rm", "--force", self.id)


def finite(container: Container, expected: int | None = None) -> tuple[int, str]:
    container.start()
    result = int(docker("wait", container.id).stdout.strip())
    if expected is not None:
        assert result == expected, f"Unexpected finite exit: {result}."
    return result, docker("logs", container.id).stdout


def orchestrator(published: Path | None = None) -> dict:
    results = {}
    denied = Container("orchestrator")
    try:
        finite(denied, 78)
        results["default_ingress_exit"] = 78
        assert not denied.state()["Running"]
    finally:
        denied.cleanup()
    # Even explicitly synthetic flags cannot bypass actual kernel containment.
    bridged = Container("orchestrator", {"ORCHESTRATOR_LOCAL_PROOF": "1"}, network="bridge")
    try:
        finite(bridged, 78)
        results["nonisolated_proof_exit"] = 78
    finally:
        bridged.cleanup()
    if published:
        results["ordinary_publication_hashes"] = verify_resources(published, False)
    proof = Container("orchestrator", {"ORCHESTRATOR_LOCAL_PROOF": "1"}, published=published)
    try:
        proof.start()
        proof.wait("/readiness")
        results.update({"sdk_readiness_status": 200, "network": "none", "externally_usable": False})
        results.update(proof.stop())
        assert results["sigterm_exit"] == 0, "Responses did not complete graceful shutdown."
    finally:
        proof.cleanup()
    return results


def http_host(service: str) -> dict:
    container = Container(service)
    try:
        container.start()
        container.wait("/api/health" if service == "api" else "/channel/health")
        assert docker("exec", container.id, "sh", "-c",
                      "test ! -w /app/resources/backend/rules && sha256sum -c /app/checksums.sha256 >/dev/null").returncode == 0
        result = {"liveness": 200, "network": "none", "nonroot_readonly_resources": True,
                  "checksums_verified": True}
        if service == "api":
            status, body = container.request("/api/ready")
            assert status == 200 and json.loads(body)["ready"] is False
            result.update({"readiness_status": status, "ready": False})
            protected = "/api/scope"
        else:
            status, body = container.request("/channel/ready")
            assert status == 200 and json.loads(body)["ready"] is True
            result["static_readiness_false_positive"] = True
            protected = "/channel/v1/tools"
        assert container.request(protected)[0] == 401
        assert container.request("/__contract__/reset", "POST")[0] == 404
        result.update({"unauthorized": 401, "contract_controls": 404})
        result.update(container.stop())
        assert result["sigterm_exit"] == 0, "HTTP host did not complete graceful shutdown."
        return result
    finally:
        container.cleanup()


def worker() -> dict:
    once = Container("worker", arguments=["--once"])
    try:
        _, output = finite(once, 0)
        assert "Processed 0 queue items." in output
    finally:
        once.cleanup()
    invalid = Container("worker", {"ENVIRONMENT": "azure"}, arguments=["--once"])
    try:
        invalid.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and invalid.state()["Running"]:
            time.sleep(0.2)
        state = invalid.state()
        if state["Running"]:
            diagnostic = docker("logs", invalid.id).stderr
            assert "Deployed hosts require Warehouse, lakehouse SQL and Blob" in diagnostic
            assert "qemu: uncaught target signal 6" in diagnostic
            invalid_exit = {"invalid_configuration_refused": True,
                            "emulated_abort_not_reaped": True, "abnormal_exit_verified": False}
        else:
            assert state["ExitCode"] != 0
            invalid_exit = {"invalid_configuration_exit": state["ExitCode"], "abnormal_exit_verified": True}
    finally:
        invalid.cleanup()
    daemon = Container("worker")
    try:
        daemon.start()
        time.sleep(2)
        assert daemon.state()["Running"]
        config = json.loads(docker("image", "inspect", "--format", "{{json .Config}}",
                                   "tcc-w4-worker:local").stdout)
        assert not config.get("ExposedPorts") and not config.get("Healthcheck")
        result = {"once_exit": 0, "progress_observed": 0, **invalid_exit,
                  "http_health_invented": False, "app_service_available": False}
        result.update(daemon.stop())
        return result
    finally:
        daemon.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published-orchestrator", action="store_true")
    args = parser.parse_args()
    if args.published_orchestrator:
        result = orchestrator(DEPLOY / ".artifacts" / "publish" / "orchestrator")
        name = "published-orchestrator-smoke.json"
    else:
        name = "container-smoke.json"
        result = {"complete": False, "services": {}}
        for service, run in (("api", lambda: http_host("api")), ("gateway", lambda: http_host("gateway")),
                             ("worker", worker), ("orchestrator", orchestrator)):
            result["services"][service] = run()
            print(f"{service}: real synthetic container checks passed.")
            (DEPLOY / ".artifacts" / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["complete"] = True
    (DEPLOY / ".artifacts" / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Synthetic container boundaries passed; evidence contains no payloads or configuration values.")


if __name__ == "__main__":
    main()
