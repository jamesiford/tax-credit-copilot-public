"""Use ordinary parent publications, but keep all mutable proof state in telemetry."""

import argparse
import hashlib
import http.server
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import probe_support as s
from receipt_checks import assert_privacy, records
from verify import start_collector

# Reuse the parent's credential-free synthetic launch contract without writing
# Python bytecode into the parent-owned deployment directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(s.ROOT.parent))
import smoke as parent_smoke


def request_status(address):
    try:
        return s.request(address)
    except urllib.error.HTTPError as error:
        return error.code


def received(service, deadline):
    while time.monotonic() < deadline:
        spans = [value for owner, value in records(s.snapshot(), "Spans") if owner == service]
        metrics = [value for owner, value in records(s.snapshot(), "Metrics") if owner == service]
        if any(value["name"] == "Microsoft.AspNetCore.Server" for value in spans) and any(
                value["name"].endswith("http.server.request.duration") for value in metrics):
            return spans, metrics
        time.sleep(0.1)
    raise AssertionError("Published host did not export a server trace and request metric")


def launch(service, endpoint, work):
    package = s.ROOT.parent / ".artifacts" / "publish" / service
    assembly = package / ("TaxCredit." + ("Api" if service == "api" else "Gateway") + ".dll")
    assert assembly.is_file(), "Parent publication is absent"
    env = parent_smoke.environment(service, package, work)
    env.update({
        "DOTNET_STARTUP_HOOKS": str(s.ARTIFACTS / "publish" / "hook" / "TaxCredit.Deployment.Telemetry.dll"),
        "TELEMETRY_ENABLED": "1", "OTEL_SERVICE_NAME": "taxcredit-" + service,
        "TELEMETRY_VERSION": s.VERSION, "TELEMETRY_ENDPOINT": endpoint,
    })
    address = f"http://127.0.0.1:{s.port()}"
    process = subprocess.Popen(
        ["dotnet", str(assembly), "--urls", address], cwd=work, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return process, address, hashlib.sha256(assembly.read_bytes()).hexdigest()


def published(service, endpoint):
    work = s.ARTIFACTS / "published-proof" / service
    work.mkdir(parents=True, exist_ok=True)
    process = None
    try:
        process, address, checksum = launch(service, endpoint, work)
        s.wait_ready(address + "/api/health", process)
        protected = "/api/scope" if service == "api" else "/channel/v1/tools"
        assert request_status(address + protected) == 401
        spans, metrics = received("taxcredit-" + service, time.monotonic() + 10)
        assert_privacy(s.snapshot())
        assert not any(value["name"] == "System.Net.Http.Client" for value in spans)
        return {
            "published_dll_sha256": checksum, "health_status": 200, "protected_status": 401,
            "server_trace_receipts": sum(value["name"] == "Microsoft.AspNetCore.Server" for value in spans),
            "metric_series_batches": len(metrics), "service_version_attribution": True,
            "actual_dependency_correlation": False,
        }
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            s.capture_diagnostics(process)
            s.assert_diagnostics(process, [])
        shutil.rmtree(work)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", action="store_true")
    args = parser.parse_args()
    s.build()
    receiver = http.server.ThreadingHTTPServer(
        ("0.0.0.0" if args.collector else "127.0.0.1", 0), s.Receiver)
    threading.Thread(target=receiver.serve_forever, daemon=True).start()
    container = None
    try:
        endpoint = f"http://127.0.0.1:{receiver.server_port}/"
        if args.collector:
            container, endpoint = start_collector(receiver)
        result = {
            "scope": "ordinary published API/gateway; synthetic local SQLite and missing CSV",
            "path": "local-linux-collector-to-receiver" if args.collector else "local-test-receiver",
            "services": {service: published(service, endpoint) for service in ("api", "gateway")},
            "privacy_allowlist": "passed", "actual_dependency_correlation": False,
            "shutdown_scope": "receipt proven before termination; no actual-host graceful-flush claim",
            "hook_sha256": hashlib.sha256(
                (s.ARTIFACTS / "publish" / "hook" / "TaxCredit.Deployment.Telemetry.dll").read_bytes()
            ).hexdigest(),
        }
        name = "published-collector.json" if args.collector else "published-receiver.json"
        (s.ROOT / "evidence" / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if container:
            s.run(["docker", "stop", "--time", "5", container])
        receiver.shutdown()
        receiver.server_close()


if __name__ == "__main__":
    main()
