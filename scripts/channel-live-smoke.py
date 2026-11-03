"""Live smoke of the deployed channel gateway, as the signed-in operator. [CH-13]

    python scripts/channel-live-smoke.py [--only catalog,reads,writes,verify,audit,limits,nonwriter]
                                         [--compare-local] [--evidence <path>]

Everything comes from the environment; nothing is written into this file:

    GATEWAY_BASE_URL    https://<gateway host>
    GATEWAY_TOKEN       a delegated token for the gateway's `Channel.Access` scope
    WRONG_TOKEN         a token for any OTHER audience (must be refused)
    SMOKE_CLIENTS       comma-separated synthetic client ids (default 2001,2002)
    SMOKE_WRITE_CLIENT  the synthetic client the write round trip changes (default 2002)
    SMOKE_PROGRAM       programme code for the write (default GA_JTC)

A person with a delegated token is the acting user, so every audit row it makes reads
`channel=cowork`, `identity_assurance=delegated`. `--compare-local` runs the same tool in
this process against the SAME Warehouse (the environment of the deployed API) and demands
identical facts. The transcript carries no token and no identifier of a person.
Exit 0 only when every check passed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

GUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
SMOKE = uuid.uuid4().hex[:8]
RESULTS: list[tuple[str, bool, str]] = []
LINES: list[str] = []


def say(text: str) -> None:
    clean = GUID.sub("<id>", text)
    LINES.append(clean)
    print(clean)


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    say(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)


class Gateway:
    """One HTTP client, a counter for correlation ids, and nothing that prints a token."""

    def __init__(self) -> None:
        self.base = os.environ["GATEWAY_BASE_URL"].rstrip("/")
        self.token = os.environ["GATEWAY_TOKEN"]
        self.http = httpx.Client(timeout=120)
        self.n = 0

    def headers(self, token: str | None = None) -> dict[str, str]:
        self.n += 1
        return {"Authorization": f"Bearer {token or self.token}", "X-Correlation-Id": f"smoke-{SMOKE}-{self.n}"}

    def call(self, tool: str, args: dict | None = None, **body) -> httpx.Response:
        return self.http.post(f"{self.base}/channel/v1/tools/{tool}", json={"args": args or {}, **body}, headers=self.headers())

    def facts(self, tool: str, args: dict | None = None) -> dict:
        response = self.call(tool, args)
        return response.json().get("facts", {}) if response.status_code == 200 else {"_status": response.status_code, "_body": response.text[:200]}

    def two_steps(self, tool: str, args: dict, key: str) -> tuple[httpx.Response, httpx.Response]:
        prepared = self.call(f"{tool}_prepare", args)
        if prepared.status_code != 200:
            return prepared, prepared
        token = prepared.json()["facts"]["confirmation"]["token"]
        return prepared, self.call(f"{tool}_commit", args, confirmation_token=token, idempotency_key=key)

    def mcp(self, method: str, params: dict | None = None, session: str | None = None) -> httpx.Response:
        headers = {**self.headers(), "Accept": "application/json, text/event-stream"}
        if session:
            headers["Mcp-Session-Id"] = session
        return self.http.post(f"{self.base}/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def run_catalog(gw: Gateway) -> None:
    from application.capabilities import catalog

    expected = {t.name for t in catalog.offered()} | {"channel_ping"}
    rest = gw.http.get(f"{gw.base}/channel/v1/tools", headers=gw.headers())
    names = {t["name"] for t in rest.json()["tools"]} if rest.status_code == 200 else set()
    check("REST tools/list equals the catalog (plus the debug ping)", names == expected, f"{len(names)} tools; missing={sorted(expected - names)} extra={sorted(names - expected)}")
    init = gw.mcp("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}})
    session = init.headers.get("mcp-session-id")
    listed = gw.mcp("tools/list", session=session)
    mcp_names = {t["name"] for t in listed.json().get("result", {}).get("tools", [])}
    check("MCP tools/list equals REST tools/list", mcp_names == names, f"{len(mcp_names)} tools")
    check("no token is a 401", gw.http.get(f"{gw.base}/channel/v1/tools").status_code == 401)
    wrong = gw.http.get(f"{gw.base}/channel/v1/tools", headers=gw.headers(os.environ.get("WRONG_TOKEN", "x")))
    check("a wrong-audience token is a 401", wrong.status_code == 401, f"got {wrong.status_code}")


def local_facts(tool: str, args: dict) -> dict:
    from application.capabilities import registry

    return registry.call(tool, **args).to_dict()["facts"]


def last_year(gw: Gateway, client: int) -> int | None:
    years = [y.get("tax_year") for y in gw.facts("client_trend", {"client_id": client}).get("years", []) if isinstance(y, dict)]
    return max((y for y in years if isinstance(y, int)), default=None)


def run_reads(gw: Gateway, clients: list[int], compare: bool) -> None:
    check("book_rank answers", "_status" not in gw.facts("book_rank", {"limit": 5}))
    for client in clients:
        year = last_year(gw, client)
        check(f"client {client}: a calculated year exists", year is not None, f"TY{year}")
        calls = {
            "client_resolve": {"name_or_text": f"client {client}"},
            "client_situation": {"client_id": client},
            "client_eligibility": {"client_id": client, "tax_year": year, "method": "both"},
            "client_trend": {"client_id": client},
            "client_at_risk": {"client_id": client, "tax_year": year},
            "client_discovery": {"client_id": client},
            "calc_walkthrough": {"client_id": client, "tax_year": year},
        }
        for tool, args in calls.items():
            got = gw.facts(tool, args)
            check(f"client {client}: {tool} answers", "_status" not in got, str(got.get("_status", "ok")))
            if compare and "_status" not in got:
                try:
                    same = got == local_facts(tool, args)
                    check(f"client {client}: {tool} facts identical to the engine's own", same)
                except Exception as exc:  # noqa: BLE001 - reported, never hidden
                    check(f"client {client}: {tool} local comparison ran", False, type(exc).__name__)


def claim_year(gw: Gateway, client: int) -> int | None:
    years = gw.facts("client_situation", {"client_id": client}).get("tax_years") or []
    return max(years, default=None)


def run_writes(gw: Gateway, client: int, program: str) -> None:
    note = f"live smoke {SMOKE}"
    args = {"client_id": client, "program_code": program, "scope": "prospective", "note": note}
    prepared, committed = gw.two_steps("engagement_set", args, f"smoke-{SMOKE}-eng")
    check("engagement_set prepare then commit", prepared.status_code == 200 and committed.status_code == 200, f"{prepared.status_code}/{committed.status_code}")
    if committed.status_code == 200:
        replay = gw.call("engagement_set_commit", args, confirmation_token=prepared.json()["facts"]["confirmation"]["token"], idempotency_key=f"smoke-{SMOKE}-eng")
        check("an idempotent retry returns the first result", replay.status_code == 200 and replay.json()["facts"].get("replayed") is True)
    year = claim_year(gw, client)
    found = gw.facts("findings_list", {"client_id": client, "tax_year": year}).get("findings") if year else None
    if found:
        resolve = {"client_id": client, "tax_year": year, "finding_id": found[0]["finding_id"], "resolution": "flag", "note": note}
        _, done = gw.two_steps("finding_resolve", resolve, f"smoke-{SMOKE}-fnd")
        check("finding_resolve prepare then commit", done.status_code == 200, str(done.status_code))
    else:
        say(f"SKIP  finding_resolve: client {client} TY{year} has no open finding to resolve")
    for step, status in (("forward", "proposed"), ("restore", "assessed")):
        cell = {"client_id": client, "program_code": program, "tax_year": year, "status": status}
        _, moved = gw.two_steps("claim_transition", cell, f"smoke-{SMOKE}-clm-{step}")
        check(f"claim_transition {step} to '{status}' (TY{year}) prepare then commit", moved.status_code == 200, str(moved.status_code))


def run_nonwriter(gw: Gateway, client: int, program: str) -> None:
    args = {"client_id": client, "program_code": program, "scope": "prospective", "note": f"live smoke {SMOKE} (must be refused)"}
    prepared = gw.call("engagement_set_prepare", args)
    check("a non-writer's change is refused", prepared.status_code == 403, f"got {prepared.status_code}")
    check("a non-writer can still read", "_status" not in gw.facts("book_rank", {"limit": 3}))


def run_verify(gw: Gateway, client: int) -> None:
    year = last_year(gw, client)
    facts = gw.facts("client_eligibility", {"client_id": client, "tax_year": year})
    numbers = [v for v in json.dumps(facts).replace('"', " ").replace(",", " ").split() if re.fullmatch(r"\d+\.\d+", v)]
    if not numbers:
        check("verify_figures has a figure to check", False, "no decimal figure in the facts")
        return
    ok = gw.facts("verify_figures", {"draft_text": f"The figure was {numbers[0]}."})
    bad = gw.facts("verify_figures", {"draft_text": f"The figure was {numbers[0]}1."})
    check("verify_figures accepts a figure from the returned facts", ok.get("status") == "pass", str(ok.get("status")))
    check("verify_figures rejects a one-digit mutation", bad.get("status") == "rejected", str(bad.get("status")))


def run_limits(gw: Gateway) -> None:
    big = gw.http.post(f"{gw.base}/channel/v1/tools/verify_figures", headers=gw.headers(), content=json.dumps({"args": {"draft_text": "x" * 70000}}))
    check("a body over the cap is a 413", big.status_code == 413, f"got {big.status_code}")
    codes = [gw.call("verify_figures", {"draft_text": "1"}).status_code for _ in range(75)]
    check("the rate limit answers 429 with a wait", 429 in codes, f"{codes.count(429)} of 75 refused")


def run_audit() -> None:
    say(f"INFO  audit rows are read with scripts/channel-audit.py --detail; this run's correlation ids start 'smoke-{SMOKE}-'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="catalog,reads,writes,verify,limits,audit")
    parser.add_argument("--compare-local", action="store_true")
    parser.add_argument("--evidence")
    args = parser.parse_args()
    steps = set(args.only.split(","))
    clients = [int(c) for c in os.environ.get("SMOKE_CLIENTS", "2001,2002").split(",")]
    write_client, program = int(os.environ.get("SMOKE_WRITE_CLIENT", "2002")), os.environ.get("SMOKE_PROGRAM", "GA_JTC")
    gw = Gateway()
    say(f"# live smoke {SMOKE}  steps={sorted(steps)}")
    plan = [("catalog", lambda: run_catalog(gw)), ("reads", lambda: run_reads(gw, clients, args.compare_local)),
            ("writes", lambda: run_writes(gw, write_client, program)), ("nonwriter", lambda: run_nonwriter(gw, write_client, program)),
            ("verify", lambda: run_verify(gw, clients[0])), ("audit", run_audit), ("limits", lambda: run_limits(gw))]
    for name, step in plan:
        if name in steps:
            say(f"## {name}")
            step()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    say(f"\nRESULT  {passed} passed, {len(RESULTS) - passed} failed, {len(RESULTS)} checks  (smoke id {SMOKE}, {time.strftime('%Y-%m-%d')})")
    if args.evidence:
        Path(args.evidence).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
