"""Own synthetic processes and in-memory receipts without persisting payloads."""

import contextlib
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
DOTNET = ROOT.parent.parent
ARTIFACTS = ROOT / ".artifacts"
POISON = "SYNTHETIC_PRIVATE_SENTINEL"
VERSION = "1.2.3"
COLLECTOR = "otel/opentelemetry-collector:0.123.0"
RUNTIME = "mcr.microsoft.com/dotnet/aspnet:10.0"
RECEIPTS = []
RECEIPT_LOCK = threading.Lock()
LINUX_CONTAINER = None
HOST_ENDPOINT = None
SERVICE_PORTS = {}


class Receiver(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        payload = self.rfile.read(int(self.headers["Content-Length"]))
        with RECEIPT_LOCK:
            RECEIPTS.append(json.loads(payload))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")


class UnavailableReceiver(http.server.BaseHTTPRequestHandler):
    """Consume without retaining payloads; emulate rejection or a stalled peer."""

    def log_message(self, *_):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.server.failure == "timeout":
            time.sleep(2)
        body = b""
        if self.server.failure == "partial_success":
            body = json.dumps({"partialSuccess": {"rejectedSpans": "1", "errorMessage": POISON}}).encode()
        elif self.server.failure == "malformed_response":
            body = POISON.encode()
        with contextlib.suppress(OSError):
            self.send_response(503 if self.server.failure in ("http_503", "timeout") else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(address, method="GET"):
    with urllib.request.urlopen(urllib.request.Request(address, method=method), timeout=5) as response:
        return response.status


def subscriptions(address):
    with urllib.request.urlopen(address + "/subscriptions", timeout=5) as response:
        return json.load(response)


def wait_ready(address, process=None):
    until = time.monotonic() + 30
    while time.monotonic() < until:
        if process and process.poll() is not None:
            raise AssertionError("Synthetic host exited before readiness")
        try:
            if request(address) == 200:
                return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise AssertionError("Synthetic listener did not become ready")


def run(command, **kwargs):
    return subprocess.run(command, cwd=DOTNET, check=True, capture_output=True, text=True, **kwargs)


def snapshot():
    with RECEIPT_LOCK:
        return list(RECEIPTS)


class DockerProbe:
    """Expose the same lifecycle operations for native processes and containers."""

    def __init__(self, container):
        self.container = container
        self.returncode = None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        state = json.loads(run(["docker", "inspect", "-f", "{{json .State}}", self.container]).stdout)
        if state["Running"]:
            return None
        self.returncode = state["ExitCode"]
        return self.returncode

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.poll() is not None:
                run(["docker", "rm", self.container])
                return self.returncode
            time.sleep(0.1)
        raise AssertionError("Linux synthetic host failed to stop")

    def kill(self):
        run(["docker", "kill", self.container])


def host_settings(endpoint, service, dependency, enabled, version, host_port):
    settings = {
        "DOTNET_STARTUP_HOOKS": str(ARTIFACTS / "publish" / "hook" / "TaxCredit.Deployment.Telemetry.dll"),
        "TELEMETRY_ENABLED": enabled,
        "OTEL_SERVICE_NAME": service,
        "TELEMETRY_VERSION": version,
        "TELEMETRY_ENDPOINT": endpoint,
        "ASPNETCORE_URLS": f"http://127.0.0.1:{host_port}",
        "Logging__LogLevel__Default": "None",
        "OTEL_RESOURCE_ATTRIBUTES": "person.id=" + POISON + ",url.full=" + POISON,
    }
    if LINUX_CONTAINER:
        settings["DOTNET_STARTUP_HOOKS"] = "/telemetry/hook/TaxCredit.Deployment.Telemetry.dll"
        settings["TELEMETRY_ENDPOINT"] = endpoint.replace(HOST_ENDPOINT, "http://127.0.0.1:4318/")
        settings["ASPNETCORE_URLS"] = f"http://0.0.0.0:{host_port}"
    if dependency:
        settings["PROBE_DEPENDENCY"] = dependency
    return settings


def spawn(settings):
    if LINUX_CONTAINER:
        command = ["docker", "run", "--detach", "--log-driver", "none", "--user", "1654",
                   "--network", "container:" + LINUX_CONTAINER, "--read-only",
                   "--mount", f"type=bind,source={ARTIFACTS / 'publish'},target=/telemetry,readonly"]
        for key, value in settings.items():
            command.extend(["--env", key + "=" + value])
        command.extend([RUNTIME, "dotnet", "/telemetry/probe/TelemetryProbe.dll"])
        return DockerProbe(run(command).stdout.strip())
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("OTEL_", "APPLICATIONINSIGHTS_", "TELEMETRY_", "TCC_TELEMETRY_", "CORECLR_")):
            del env[key]
    env.pop("PROBE_DEPENDENCY", None)
    env.update(settings)
    return subprocess.Popen(
        ["dotnet", str(ARTIFACTS / "publish" / "probe" / "TelemetryProbe.dll")],
        cwd=DOTNET, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def start_host(endpoint, service, dependency=None, enabled="1", version=VERSION):
    host_port = SERVICE_PORTS.get(service, port())
    process = spawn(host_settings(endpoint, service, dependency, enabled, version, host_port))
    address = f"http://127.0.0.1:{host_port}"
    try:
        wait_ready(address + "/ready", process)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        raise
    return process, address


def stop_host(process, address):
    started = time.monotonic()
    if isinstance(process, DockerProbe):
        run(["docker", "kill", "--signal", "TERM", process.container])
    else:
        with contextlib.suppress(OSError, urllib.error.URLError):
            request(address + "/stop", "POST")
    process.wait(timeout=8)
    assert process.returncode == 0
    capture_diagnostics(process)
    return round(time.monotonic() - started, 3)


def capture_diagnostics(process):
    if isinstance(process, DockerProbe):
        return
    lines = process.stderr.read().decode("utf-8").splitlines()
    process.stderr.close()
    allowed = {"TCC_TELEMETRY_INVALID_CONFIGURATION", "TCC_TELEMETRY_EXPORT_FAILED"}
    assert set(lines) <= allowed, "Diagnostic content escaped the fixed-code allowlist"
    assert all(lines.count(code) <= 1 for code in allowed), "Diagnostic was not once per process"
    process.diagnostic_codes = lines


def assert_diagnostics(process, expected):
    if not isinstance(process, DockerProbe):
        assert process.diagnostic_codes == expected, "Expected fixed telemetry diagnostic was absent"


@contextlib.contextmanager
def owned_processes():
    processes = []
    try:
        yield processes
    finally:
        for process, _ in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def build():
    ARTIFACTS.mkdir(exist_ok=True)
    for project, output in (
        ("Hook/TaxCredit.Deployment.Telemetry.csproj", "hook"),
        ("Probe/TelemetryProbe.csproj", "probe"),
    ):
        project_path = ROOT.joinpath(*project.split("/"))
        run(["dotnet", "publish", str(project_path), "-c", "Release", "--nologo",
             "-v", "quiet", "-o", str(ARTIFACTS / "publish" / output)])
