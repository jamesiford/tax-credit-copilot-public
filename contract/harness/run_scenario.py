"""Run ONE scenario in a fresh process, so no state, cache, rate-limit bucket or counter leaks from another scenario.

    python -m contract.harness.run_scenario --scenario contract/scenarios/<name>.json --out <file.jsonl>
    python -m contract.harness.run_scenario --scenario ... --base-url http://127.0.0.1:PORT --out ...   # against a running server
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from contract.harness import hermetic  # noqa: E402


async def _in_process(scenario: dict) -> list[dict]:
    from contract import exchange
    from contract.harness import world

    built = world.build(scenario["profile"])
    if scenario.get("auth"):
        from contract.harness import auth

        auth.install(int((scenario["auth"] if isinstance(scenario["auth"], dict) else {}).get("rate_limit_per_minute", 3)))
    for name, value in (scenario.get("env") or {}).items():  # after the build: hermetic pins would otherwise win
        os.environ[name] = str(value)
    async with built.client() as http:
        return await exchange.run_scenario(http, scenario)


async def _remote(scenario: dict, base_url: str) -> list[dict]:
    import httpx

    from contract import exchange

    async with httpx.AsyncClient(base_url=base_url, timeout=300, limits=httpx.Limits(max_keepalive_connections=0)) as http:  # see replay.run_against
        return await exchange.run_scenario(http, scenario)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    from contract import oracle

    oracle.require()
    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    if args.base_url:
        records = asyncio.run(_remote(scenario, args.base_url))
    else:
        hermetic.apply()
        records = asyncio.run(_in_process(scenario))
    from contract import exchange

    Path(args.out).write_text("".join(exchange.dump_record(r) + "\n" for r in records), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
