"""Scripted live checks that need no person, against a NAMED NON-PRODUCTION API. [F07.6]

    python scripts/live-check-api.py --target <name> bounds                   # live check 25 (refusals only: writes nothing)
    python scripts/live-check-api.py --target <name> bounds --allow-writes    # also: a draft name of exactly 200 characters is accepted (then withdrawn)
    python scripts/live-check-api.py --target <name> rate-limit --limit 60    # the per-caller limit trips with a 429 and Retry-After

Run `scripts/live-smoke.py` first. Targets and the production guard are the same as there (`SMOKE_TARGETS`, `SMOKE_PRODUCTION_TARGETS`,
a name containing "prod" is refused without `--allow-production`); `local` is the loopback API. A bearer token, when needed, comes from the
variable named by `--token-env` (default SMOKE_TOKEN).

What each check does, and what it cannot do:

- `bounds` sends a draft name of 201 characters, a review comment of 2001, a batch filter value of 65 characters and a 13-year `tax_years`,
  and expects a 422 for each (a refusal, never a store error: a 500 is the failure this catches). Those requests are refused before anything
  is stored. With `--allow-writes` it also creates a draft whose name is exactly 200 characters (the limit must be accepted) and withdraws it.
- `rate-limit` makes `--limit` + 1 batch previews as one caller and expects the last to be a 429 with a `Retry-After`. It spends that
  caller's budget for a minute, nothing else; it needs a signed-in caller (the limit is off when nobody is signed in) and a sandbox whose
  `RATE_LIMIT_PER_MINUTE` equals `--limit`.

Exit 0 when every expectation held, 1 when one did not, 2 on usage, 3 when the target guard refused. Nothing here is run by the build.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_GUARD = 0, 1, 2, 3
DRAFTS = "/api/v2/program-drafts"
BATCHES = "/api/v2/run-batches"


def _smoke():
    """The read-only smoke script's target guard and error-code reader, loaded by path (its name has a hyphen)."""
    spec = importlib.util.spec_from_file_location("live_smoke", Path(__file__).with_name("live-smoke.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("live_smoke", module)
    spec.loader.exec_module(module)
    return module


@dataclass
class Outcome:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list)

    def expect(self, name: str, ok: bool, detail: str = "") -> None:
        self.outcomes.append(Outcome(name, ok, detail))

    @property
    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.ok]


def _refused(client: httpx.Client, report: Report, name: str, response: httpx.Response) -> None:
    code = _smoke().error_code(response) if response.status_code >= 400 else ""
    report.expect(name, response.status_code == 422, f"{response.status_code} {code}".strip())


def check_bounds(client: httpx.Client, *, allow_writes: bool = False) -> Report:
    """The four refusals of live check 25, and with `allow_writes` the at-limit acceptance."""
    report = Report()
    code = "ZZ_LIVE_" + uuid.uuid4().hex[:8].upper()
    _refused(client, report, "draft name of 201 characters", client.post(
        DRAFTS, json={"code": code, "name": "n" * 201, "state": "ZZ", "years": []}))
    _refused(client, report, "review comment of 2001 characters", client.post(
        f"{DRAFTS}/{uuid.uuid4().hex}/review", json={"decision": "request_changes", "comment": "c" * 2001}))
    start = {"kind": "calculate", "dry_run": True}
    _refused(client, report, "batch filter value of 65 characters", client.post(
        BATCHES, json={**start, "scope": {"kind": "filter", "filter": {"state": "G" * 65}}}))
    _refused(client, report, "tax_years of 13 years", client.post(
        BATCHES, json={**start, "scope": {"kind": "all"}, "tax_years": list(range(2013, 2026))}))
    if allow_writes:
        made = client.post(DRAFTS, json={"code": code, "name": "n" * 200, "state": "ZZ", "years": []})
        report.expect("draft name of exactly 200 characters is accepted", made.status_code == 201, str(made.status_code))
        if made.status_code == 201:
            client.post(f"{DRAFTS}/{made.json()['draft_id']}/withdraw", json={"reason": "live check 25"})
    return report


def check_rate_limit(client: httpx.Client, *, limit: int) -> Report:
    """The (limit + 1)th batch preview of one caller is a 429 with `Retry-After`; the first `limit` are not."""
    report = Report()
    body = {"kind": "calculate", "dry_run": True, "scope": {"kind": "list", "client_ids": []}}
    seen = [client.post(BATCHES, json=body) for _ in range(limit + 1)]
    report.expect("the first requests are not limited", all(r.status_code != 429 for r in seen[:limit]),
                  f"{limit} requests")
    last = seen[-1]
    report.expect("the next request is a 429", last.status_code == 429, str(last.status_code))
    report.expect("it says when to retry", bool(last.headers.get("retry-after")), last.headers.get("retry-after", "no Retry-After"))
    return report


def render(report: Report) -> str:
    lines = [f"{'ok  ' if o.ok else 'FAIL'} {o.name}" + (f"  [{o.detail}]" if o.detail else "") for o in report.outcomes]
    lines.append(f"{len(report.outcomes) - len(report.failures)} of {len(report.outcomes)} expectations held")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="'local' or a name listed in SMOKE_TARGETS")
    parser.add_argument("--allow-production", action="store_true", help="permit a production target (never for these checks)")
    parser.add_argument("--token-env", default="SMOKE_TOKEN")
    parser.add_argument("check", choices=("bounds", "rate-limit"))
    parser.add_argument("--allow-writes", action="store_true", help="bounds: also create and withdraw one draft")
    parser.add_argument("--limit", type=int, default=60, help="rate-limit: the sandbox's RATE_LIMIT_PER_MINUTE")
    args = parser.parse_args(argv)
    smoke = _smoke()
    try:
        base_url = smoke.resolve_target(args.target, dict(os.environ), allow_production=args.allow_production)
    except smoke.TargetRefused as exc:
        print(f"GUARD REFUSED: {exc}", file=sys.stderr)
        return EXIT_GUARD
    token = os.environ.get(args.token_env)
    headers: dict[str, Any] = {"Authorization": f"Bearer {token}"} if token else {}
    print(f"target {args.target}: {base_url} ({args.check})")
    with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as client:
        report = check_bounds(client, allow_writes=args.allow_writes) if args.check == "bounds" else check_rate_limit(client, limit=args.limit)
    print(render(report))
    return EXIT_FAILED if report.failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
