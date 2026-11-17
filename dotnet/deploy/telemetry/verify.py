"""Reproduce receipt proofs and persist only sanitized aggregate evidence."""

import argparse
import hashlib
import http.server
import json
import socket
import threading
import time

import probe_support as s
from receipt_checks import verify


def start_collector(receiver):
    collector_port = s.port()
    command = [
        "docker", "run", "--detach", "--rm", "--log-driver", "none",
        "--publish", f"127.0.0.1:{collector_port}:4318",
        "--mount", f"type=bind,source={s.ROOT / 'collector.yaml'},target=/etc/otelcol/config.yaml,readonly",
        "--env", f"TCC_RECEIPT_ENDPOINT=http://host.docker.internal:{receiver.server_port}",
    ]
    for service_port in s.SERVICE_PORTS.values():
        command.extend(["--publish", f"127.0.0.1:{service_port}:{service_port}"])
    command.extend([s.COLLECTOR, "--config=/etc/otelcol/config.yaml"])
    container = s.run(command).stdout.strip()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", collector_port), timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        assert s.run(["docker", "inspect", "-f", "{{.State.Running}}", container]).stdout.strip() == "true"
        return container, f"http://127.0.0.1:{collector_port}/"
    except BaseException:
        s.run(["docker", "stop", "--time", "5", container])
        raise


def evidence(result, args):
    result.update({
        "path": "local-linux-collector-to-receiver" if args.collector else "local-test-receiver",
        "sdk": s.run(["dotnet", "--version"]).stdout.strip(),
        "collector_image": s.COLLECTOR if args.collector else None,
        "runtime": s.RUNTIME if args.linux else "local-dotnet",
        "linux_sigterm": args.linux,
        "scope": "synthetic deployment probe; actual ServiceDefaults compiled unchanged",
        "hook_sha256": hashlib.sha256(
            (s.ARTIFACTS / "publish" / "hook" / "TaxCredit.Deployment.Telemetry.dll").read_bytes()
        ).hexdigest(),
    })
    for image, key in ((s.COLLECTOR, "collector"), (s.RUNTIME, "runtime")):
        if (key == "collector" and args.collector) or (key == "runtime" and args.linux):
            result[key + "_digest"] = s.run([
                "docker", "image", "inspect", "-f", "{{index .RepoDigests 0}}", image
            ]).stdout.strip()
    if args.collector:
        result["docker_engine_architecture"] = s.run([
            "docker", "version", "--format", "{{.Server.Arch}}"
        ]).stdout.strip()
    if args.linux:
        result["runtime_architecture"] = s.run([
            "docker", "image", "inspect", "-f", "{{.Architecture}}", s.RUNTIME
        ]).stdout.strip()
    directory = s.ROOT / "evidence"
    directory.mkdir(exist_ok=True)
    name = "linux.json" if args.linux else "collector.json" if args.collector else "receiver.json"
    (directory / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", action="store_true", help="Route through pinned local Linux collector")
    parser.add_argument("--linux", action="store_true", help="Also run all probes as nonroot Linux containers")
    args = parser.parse_args()
    if args.linux:
        args.collector = True
        for service in ("taxcredit-api", "taxcredit-gateway", "taxcredit-worker",
                        "taxcredit-orchestrator", s.POISON):
            s.SERVICE_PORTS[service] = s.port()
    s.build()
    receiver = http.server.ThreadingHTTPServer(
        ("0.0.0.0" if args.collector else "127.0.0.1", 0), s.Receiver)
    threading.Thread(target=receiver.serve_forever, daemon=True).start()
    container = None
    try:
        endpoint = f"http://127.0.0.1:{receiver.server_port}/"
        if args.collector:
            container, endpoint = start_collector(receiver)
            if args.linux:
                s.LINUX_CONTAINER, s.HOST_ENDPOINT = container, endpoint
        evidence(verify(endpoint, 1.5 if args.collector else 0.15), args)
    finally:
        if container:
            s.run(["docker", "stop", "--time", "5", container])
        receiver.shutdown()
        receiver.server_close()


if __name__ == "__main__":
    main()
