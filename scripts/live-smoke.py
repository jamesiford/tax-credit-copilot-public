"""Read-only smoke of a RUNNING API: the first thing to run after any deploy. [F07.1]

    python scripts/live-smoke.py --target local
    python scripts/live-smoke.py --target <name>            # <name>=<https url> in SMOKE_TARGETS
    python scripts/live-smoke.py --target <name> --allow-production    # a name containing "prod", or listed in
                                                                         # SMOKE_PRODUCTION_TARGETS

Why it exists: a driver-level mistake (a timeout set on a cursor, which the driver does not allow) passed every test
and returned 500 on every live portfolio read. Tests cannot see that; one real GET of each read endpoint can.

What it does: only HTTP GET (the client refuses any other method), to `/api/ready`, `/api/scope`, `/api/v2/portfolio`,
`/api/v2/programs`, `/api/v2/run-batches`, `/api/rules` and, for each client in scope, its scope, eligibility and unit
trend for the default year. Every non-2xx is reported with the error code from the response body (a `code`, or a short
slug of the detail text: never the whole body, never a token). Exit 0 when everything answered 2xx, 1 when any did not,
2 on usage, 3 when the target guard refused.

Targets: `local` is the loopback API (`SMOKE_LOCAL_URL`, default http://127.0.0.1:8000). Any other name must be listed
in `SMOKE_TARGETS` as `name=url` pairs separated by commas; there is no way to point it at an arbitrary URL. A bearer
token, when the API needs one, comes from the environment variable named by `--token-env` (default SMOKE_TOKEN).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_GUARD = 0, 1, 2, 3
GLOBAL_READS = (
    "/api/ready",
    "/api/scope",
    "/api/v2/portfolio",
    "/api/v2/programs",
    "/api/v2/run-batches",
    "/api/rules",
)
_LOOPBACK = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)")


class TargetRefused(Exception):
    """The named target is unknown, or it is production and the operator did not say so."""


@dataclass
class Check:
    path: str
    status: int
    code: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


def resolve_target(name: str, env: dict[str, str], *, allow_production: bool = False) -> str:
    """The base URL for a named target, or `TargetRefused`."""
    if name == "local":
        url = env.get("SMOKE_LOCAL_URL", "http://127.0.0.1:8000")
        if not _LOOPBACK.match(url):
            raise TargetRefused(f"`local` must be a loopback address, not {url}")
        return url.rstrip("/")
    known = dict(pair.split("=", 1) for pair in env.get("SMOKE_TARGETS", "").split(",") if "=" in pair)
    if name not in known:
        raise TargetRefused(f"unknown target '{name}': list it in SMOKE_TARGETS as name=url (known: {', '.join(sorted(known)) or 'none'})")
    protected = {t.strip() for t in env.get("SMOKE_PRODUCTION_TARGETS", "").split(",") if t.strip()}
    if (name in protected or "prod" in name.lower()) and not allow_production:
        raise TargetRefused(f"'{name}' is a production target: re-run with --allow-production to read it")
    return known[name].rstrip("/")


def error_code(response: httpx.Response) -> str:
    """A short, safe description of why a call failed: the body's code, else a slug of its detail, never the body."""
    try:
        body: Any = response.json()
    except ValueError:
        return f"http_{response.status_code}"
    if isinstance(body, dict):
        detail = body.get("detail", body.get("error"))
        for holder in (body, detail if isinstance(detail, dict) else {}):
            if isinstance(holder.get("code"), str):
                return holder["code"][:60]
        if isinstance(detail, str):
            return re.sub(r"[^a-z0-9]+", "_", detail.lower()).strip("_")[:60] or f"http_{response.status_code}"
        if isinstance(detail, list):
            return "validation_error"
    return f"http_{response.status_code}"


def _get(client: httpx.Client, path: str, report: Report) -> dict[str, Any] | None:
    response = client.get(path)
    code = "" if 200 <= response.status_code < 300 else error_code(response)
    report.checks.append(Check(path, response.status_code, code))
    if not 200 <= response.status_code < 300:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _client_reads(client: httpx.Client, account_id: int, report: Report) -> None:
    scope = _get(client, f"/api/scope/client/{account_id}", report)
    if not scope or not scope.get("default_year") or not scope.get("states"):
        return
    year, state = scope["default_year"], scope["states"][0]
    _get(client, f"/api/eligibility/{year}?state={state}&account_id={account_id}&limit=1", report)
    _get(client, f"/api/v2/clients/{account_id}/units?year={year}&limit=1", report)


def run_smoke(client: httpx.Client) -> Report:
    """Every read, for every client the scope lists. GET only; a failure of one read never stops the others."""
    report = Report()
    bodies = {path: _get(client, path, report) for path in GLOBAL_READS}
    for entry in (bodies.get("/api/scope") or {}).get("clients", []):
        if isinstance(entry.get("account_id"), int):
            _client_reads(client, entry["account_id"], report)
    return report


class _ReadOnly(httpx.BaseTransport):
    """Refuses anything but GET before a request leaves the process."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise TargetRefused(f"live-smoke is read-only; refused {request.method} {request.url.path}")
        return self._inner.handle_request(request)


def build_client(base_url: str, token: str | None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base_url, headers=headers, timeout=60.0, transport=_ReadOnly(httpx.HTTPTransport()))


def render(report: Report) -> str:
    lines = [f"{'ok  ' if c.ok else 'FAIL'} {c.status} {c.path}" + (f"  [{c.code}]" if c.code else "") for c in report.checks]
    lines.append(f"{len(report.checks) - len(report.failures)} of {len(report.checks)} reads answered 2xx")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="'local' or a name listed in SMOKE_TARGETS")
    parser.add_argument("--allow-production", action="store_true", help="permit a production target")
    parser.add_argument("--token-env", default="SMOKE_TOKEN", help="environment variable holding a bearer token, if the API needs one")
    args = parser.parse_args(argv)
    try:
        base_url = resolve_target(args.target, dict(os.environ), allow_production=args.allow_production)
    except TargetRefused as exc:
        print(f"GUARD REFUSED: {exc}", file=sys.stderr)
        return EXIT_GUARD
    print(f"target {args.target}: {base_url} (GET only)")
    with build_client(base_url, os.environ.get(args.token_env)) as client:
        report = run_smoke(client)
    print(render(report))
    return EXIT_FAILED if report.failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
