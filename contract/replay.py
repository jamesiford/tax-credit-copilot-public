"""Replay the recordings against ANY HTTP server and report every difference.

    python -m contract.replay --base-url http://localhost:5000 --reset-url http://localhost:5000/__contract__/reset [--profile P1] [--scenario NAME] [--mode strict|semantic]
    python -m contract.replay --spawn-python [--profile P1] ...     # starts the Python API on a free port per scenario (real uvicorn)
    python -m contract.replay --in-process  ...                     # the hermetic in-process harness, one process per scenario

Server contract for a non-Python implementation (see `harness/control.py`): each scenario must start from the profile's seed
(`contract/seed/<profile>/`); the tool POSTs `--reset-url` before every scenario to get that, or you start a fresh server per scenario.
`POST /__contract__/drain` and `POST /__contract__/env` are used by the scenarios that contain control steps.

Exit status: 0 identical (strict) or identical apart from tolerated categories (semantic); 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contract import compare, exchange, normalise  # noqa: E402

SCENARIOS = ROOT / "contract" / "scenarios"
PYTHON = os.environ.get("CONTRACT_PYTHON", r"C:\Projects\GitHub\tax-credit-copilot-public\.venv\Scripts\python.exe")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def spawn_server(profile: str, auth_rate_limit: int = 0) -> tuple[subprocess.Popen, str]:
    port = free_port()
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen([PYTHON, "-m", "contract.harness.server", "--profile", profile, "--port", str(port)] + (["--auth-rate-limit", str(auth_rate_limit)] if auth_rate_limit else []), cwd=ROOT / "backend", env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    deadline = time.time() + 600
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line.startswith("READY"):
            return proc, f"http://127.0.0.1:{port}"
        if proc.poll() is not None:
            raise RuntimeError("the Python server exited before it was ready")
    proc.kill()
    raise RuntimeError("the Python server did not become ready")


def auth_limit(name: str) -> int:
    auth = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8")).get("auth")
    return 0 if not auth else int((auth if isinstance(auth, dict) else {}).get("rate_limit_per_minute", 3))


async def run_against(base_url: str, scenario: dict) -> list[dict]:
    import httpx

    async with httpx.AsyncClient(base_url=base_url, timeout=300) as http:
        return await exchange.run_scenario(http, scenario)


def replay_one(name: str, base_url: str, mode: str) -> dict:
    scenario = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))
    actual = exchange.roundtrip(normalise.apply_all(asyncio.run(run_against(base_url, scenario))))
    expected = exchange.load_records((recordings_dir() / f"{name}.jsonl").read_text(encoding="utf-8"))
    failures, tolerated = [], []
    if len(expected) != len(actual):
        failures.append({"scenario": name, "case": "(scenario)", "category": "array-length", "path": "records", "expected": len(expected), "actual": len(actual)})
    for e, a in zip(expected, actual):
        diffs = compare.compare_record(e, a)
        bad, ok = compare.split(diffs, mode)
        route = f"{e['request']['method']} {e['request']['path']}" if "request" in e else "(control)"
        for d in bad:
            failures.append({"scenario": name, "case": e["id"], "route": route, **d})
        for d in ok:
            tolerated.append({"scenario": name, "case": e["id"], "route": route, **d})
    return {"scenario": name, "exchanges": len(expected), "failures": failures, "tolerated": tolerated}


def markdown(report: dict) -> str:
    lines = [f"# Replay report ({report['mode']})", "", f"- scenarios: {len(report['scenarios'])}", f"- exchanges compared: {report['exchanges']}",
             f"- failures: {report['failure_count']}", f"- tolerated (semantic mode only): {report['tolerated_count']}", ""]
    for s in report["scenarios"]:
        lines.append(f"## {s['scenario']}: {s['exchanges']} exchanges, {len(s['failures'])} failures, {len(s['tolerated'])} tolerated")
        for d in s["failures"][:200]:
            lines.append(f"- `{d.get('route')}` / `{d['case']}` **{d['category']}** at `{d['path']}`: expected `{d['expected']}` actual `{d['actual']}`")
        for d in s["tolerated"][:50]:
            lines.append(f"- (tolerated) `{d.get('route')}` / `{d['case']}` **{d['category']}** at `{d['path']}`: expected `{d['expected']}` actual `{d['actual']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--reset-url")
    parser.add_argument("--spawn-python", action="store_true")
    parser.add_argument("--in-process", action="store_true")
    parser.add_argument("--profile", choices=["P1", "P2"])
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--mode", choices=["strict", "semantic"], default="strict")
    parser.add_argument("--recordings", help="a directory of recordings to use instead of contract/recordings (the mutation self-test)")
    parser.add_argument("--out", default=None, help="write <out>.json and <out>.md")
    args = parser.parse_args()
    if args.recordings:
        os.environ["CONTRACT_RECORDINGS"] = args.recordings
    names = []
    for f in sorted(SCENARIOS.glob("*.json")):
        scenario = json.loads(f.read_text(encoding="utf-8"))
        if (not args.profile or scenario["profile"] == args.profile) and (not args.scenario or f.stem in args.scenario):
            names.append((f.stem, scenario["profile"]))
    if not (args.base_url or args.spawn_python or args.in_process):
        parser.error("choose --base-url, --spawn-python or --in-process")
    results = []
    for name, profile in names:
        proc = None
        try:
            if args.spawn_python:
                proc, url = spawn_server(profile, auth_limit(name))
                results.append(replay_one(name, url, args.mode))
            elif args.in_process:
                results.append(run_in_process(name, args.mode))
            else:
                if args.reset_url:
                    urllib.request.urlopen(urllib.request.Request(args.reset_url, method="POST", data=b"{}"))
                results.append(replay_one(name, args.base_url, args.mode))
        finally:
            if proc is not None:
                proc.kill()
        r = results[-1]
        print(f"{name}: {r['exchanges']} exchanges, {len(r['failures'])} failures, {len(r['tolerated'])} tolerated", flush=True)
    report = {"mode": args.mode, "scenarios": results, "exchanges": sum(r["exchanges"] for r in results),
              "failure_count": sum(len(r["failures"]) for r in results), "tolerated_count": sum(len(r["tolerated"]) for r in results)}
    if args.out:
        Path(args.out + ".json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        Path(args.out + ".md").write_text(markdown(report), encoding="utf-8")
    print(f"TOTAL: {report['exchanges']} exchanges, {report['failure_count']} failures, {report['tolerated_count']} tolerated ({args.mode})")
    return 1 if report["failure_count"] else 0


def run_in_process(name: str, mode: str) -> dict:
    """The recorder's own transport, in a child process, then the same comparison."""
    import tempfile

    out = Path(tempfile.mkdtemp()) / f"{name}.jsonl"
    cmd = [PYTHON, "-m", "contract.harness.run_scenario", "--scenario", str(SCENARIOS / f"{name}.json"), "--out", str(out)]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(cmd, cwd=ROOT / "backend", env=env, check=True, capture_output=True)
    actual = normalise.apply_all(exchange.load_records(out.read_text(encoding="utf-8")))
    expected = exchange.load_records((recordings_dir() / f"{name}.jsonl").read_text(encoding="utf-8"))
    failures, tolerated = [], []
    for e, a in zip(expected, actual):
        bad, ok = compare.split(compare.compare_record(e, a), mode)
        route = f"{e['request']['method']} {e['request']['path']}" if "request" in e else "(control)"
        failures += [{"scenario": name, "case": e["id"], "route": route, **d} for d in bad]
        tolerated += [{"scenario": name, "case": e["id"], "route": route, **d} for d in ok]
    if len(expected) != len(actual):
        failures.append({"scenario": name, "case": "(scenario)", "category": "array-length", "path": "records", "expected": len(expected), "actual": len(actual)})
    return {"scenario": name, "exchanges": len(expected), "failures": failures, "tolerated": tolerated}


def recordings_dir() -> Path:
    return Path(os.environ.get("CONTRACT_RECORDINGS") or ROOT / "contract" / "recordings")


if __name__ == "__main__":
    raise SystemExit(main())
