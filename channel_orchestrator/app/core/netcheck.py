"""`/netcheck`: where can this container actually connect to? [CH-14]

The hosted runtime answered with `ConnectError` to the Foundry model endpoint while its calls to the
gateway and to the platform's own storage succeeded, and nothing in the logs said why. This answers the
questions that separate the causes: does the name resolve, to a private or a public address; does a TCP
connection open; does TLS finish; does the host answer an unauthenticated request; and does the very HTTP
client the model path uses (httpx, which honours proxy variables) agree with the plain socket.

It is offered only with `CHANNEL_DEBUG_WHOAMI`, reports host names, addresses, timings and status codes,
and never a token, a header or a response body. Environment variables are reported by NAME; the only
values shown are the non-secret ones listed in `SAFE_VALUES`.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import ssl
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

SAFE_VALUES = ("FOUNDRY_MODEL", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "AI_PROVIDER_CHAIN", "CHANNEL_NAME", "CHANNEL_IDENTITY_SOURCES")
NAME_PREFIXES = ("FOUNDRY_", "AI_", "AZURE_AI_", "CHANNEL_")
PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy")
CONTROL_HOST = "www.microsoft.com"
LOGIN_HOST = "login.microsoftonline.com"


class NetProbe:
    """The three network operations, in one place so tests can replace them without a network."""

    def resolve(self, host: str) -> list[str]:
        """Every address the name resolves to (IPv4 and IPv6), in the order the resolver gave."""
        seen: list[str] = []
        for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
            address = info[4][0]
            if address not in seen:
                seen.append(address)
        return seen

    def connect(self, address: str, timeout: float) -> None:
        """Open and close a TCP connection to port 443; raises on failure."""
        with socket.create_connection((address, 443), timeout=timeout):
            pass

    def tls_and_get(self, host: str, address: str, timeout: float) -> int:
        """Finish TLS against `host` over `address` and return the status of an unauthenticated GET /."""
        raw = socket.create_connection((address, 443), timeout=timeout)
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
            tls.settimeout(timeout)
            tls.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: tcc-netcheck\r\n\r\n".encode("ascii"))
            first = tls.recv(64).split(b"\r\n", 1)[0].decode("ascii", "replace")
        parts = first.split()
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    def httpx_get(self, url: str, timeout: float) -> int:
        """The status of an unauthenticated GET through httpx with its default (environment-honouring) setup."""
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=timeout)) as client:
            return client.get(url).status_code


def classify(address: str) -> str:
    """`private`, `loopback`, `link-local` or `public` for one address."""
    ip = ipaddress.ip_address(address)
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    return "private" if ip.is_private else "public"


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:120]}"


def check_host(probe: NetProbe, host: str, *, timeout: float = 10.0, httpx_path: str | None = None) -> dict[str, Any]:
    """Everything observable about reaching `host:443`, one key per step; a failed step stops the later ones."""
    report: dict[str, Any] = {"host": host}
    try:
        addresses = probe.resolve(host)
    except Exception as exc:  # noqa: BLE001 - the failure IS the finding
        return {**report, "resolve": _error(exc)}
    report["resolved"] = [{"address": a, "kind": classify(a)} for a in addresses]
    first = next((a for a in addresses if ":" not in a), addresses[0] if addresses else None)
    if first is None:
        return {**report, "resolve": "no addresses"}
    started = time.monotonic()
    try:
        probe.connect(first, timeout)
        report["tcp"] = {"ok": True, "ms": round((time.monotonic() - started) * 1000), "address": first}
    except Exception as exc:  # noqa: BLE001
        return {**report, "tcp": {"ok": False, "ms": round((time.monotonic() - started) * 1000), "error": _error(exc)}}
    try:
        report["tls_get_status"] = probe.tls_and_get(host, first, timeout)
    except Exception as exc:  # noqa: BLE001
        report["tls_get_status"] = _error(exc)
    if httpx_path is not None:
        try:
            report["httpx_status"] = probe.httpx_get(f"https://{host}{httpx_path}", timeout)
        except Exception as exc:  # noqa: BLE001
            report["httpx_status"] = _error(exc)
    return report


def account_hosts(project_endpoint: str) -> list[tuple[str, str | None]]:
    """The hosts around a Foundry project: its own, and the account's two other public names."""
    host = urlparse(project_endpoint).netloc
    if not host:
        return []
    account = host.split(".", 1)[0]
    return [(host, "/openai/v1/models"), (f"{account}.openai.azure.com", "/openai/models?api-version=2024-10-21"),
            (f"{account}.cognitiveservices.azure.com", None)]


def environment_report(env: Mapping[str, str]) -> dict[str, Any]:
    """Variable NAMES by group, the non-secret values, and which proxy variables exist (never their values)."""
    names = sorted(n for n in env if n.startswith(NAME_PREFIXES))
    return {
        "names": names,
        "values": {n: env[n] for n in SAFE_VALUES if n in env},
        "proxy_variables_set": sorted(n for n in PROXY_NAMES if env.get(n)),
    }


def run_netcheck(*, env: Mapping[str, str], project_endpoint: str, gateway_url: str, providers: tuple[str, ...],
                 probe: NetProbe | None = None) -> str:
    """The whole report as JSON text."""
    probe = probe or NetProbe()
    targets: list[tuple[str, str | None]] = account_hosts(project_endpoint)
    if gateway_url:
        targets.append((urlparse(gateway_url).netloc, "/channel/health"))
    targets += [(LOGIN_HOST, None), (CONTROL_HOST, None)]
    return json.dumps({
        "providers": list(providers), "environment": environment_report(env),
        "targets": [check_host(probe, host, httpx_path=path) for host, path in targets if host],
    }, indent=2)
