"""Small sequential local reads measure HTTP, not engine or live Warehouse throughput."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
import hashlib
import json
import platform
import statistics
import time

from admission import ROOT
from catalogue import CASES
from hermetic import artifact_directory, host
from safe_compare import compare_document
from sampling import timing_summary
from transport import Target, read


async def measure(case: str, clients: dict, targets: dict) -> dict:
    observations, samples = {"python": [], "dotnet": []}, []
    for ordinal in range(1, 7):
        responses = {}
        order = ("python", "dotnet") if ordinal % 2 else ("dotnet", "python")
        for name in order:
            started = time.perf_counter()
            try:
                responses[name] = await read(clients[name], targets[name], case, 1001, 2025)
                outcome = "response"
            except Exception:  # noqa: BLE001 - failed observations remain counted, no transport text
                outcome = "failed"
            observations[name].append({"sample": ordinal, "phase": "first-read" if ordinal == 1 else "warm",
                                       "order": order.index(name) + 1,
                                       "http_success": 200 <= responses[name]["status"] < 300 if name in responses else False,
                                       "ms": round((time.perf_counter() - started) * 1000, 3), "outcome": outcome})
        if len(responses) == 2:
            samples.append(compare_document({"case": case, "expected": responses["python"],
                                             "actual": responses["dotnet"], "sample": ordinal}))
        else:
            samples.append({"sample": ordinal, "verdict": "transport-or-bound", "semantic_equal": False})
    summaries = {name: {"first_read": rows[0], "warm": timing_summary(rows[1:])} for name, rows in observations.items()}
    medians = [summaries[name]["warm"]["median_ms"] for name in ("python", "dotnet")]
    delta = round(medians[1] - medians[0], 3) if all(value is not None for value in medians) else None
    return {"route": CASES[case].route, "planned_pairs": 6, "observations": observations, "summaries": summaries,
            "semantic_matches": sum(sample["semantic_equal"] for sample in samples), "samples": samples,
            "warm_dotnet_minus_python_ms": delta}


async def measurements(urls: dict) -> dict:
    import httpx

    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    targets = {name: Target(url, local=True) for name, url in urls.items()}
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False, limits=limits) as python, \
            httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False, limits=limits) as dotnet:
        return {case: await measure(case, {"python": python, "dotnet": dotnet}, targets)
                for case in ("health", "eligibility", "drafts")}


def main() -> None:
    from contract.replay_setup import prepare_external

    output = artifact_directory("paired")
    with ExitStack() as stack:
        urls = {name: stack.enter_context(host(kind, output / name))[0]
                for name, kind in (("python", "python"), ("dotnet", "api"))}
        # The fresh oracle process already built P1; its public control has no reset operation.
        prepare_external(urls["dotnet"], urls["dotnet"] + "/__contract__/reset", {"profile": "P1"})
        results = asyncio.run(measurements(urls))
    manifest = ROOT / "contract" / "seed" / "P1" / "manifest.json"
    report = {"classification": "isolated synthetic; no Fabric", "product_revision": "006760b",
              "python": platform.python_version(), "dotnet": "net10.0 Release", "sdk": "10.0.404",
              "topology": "independent ordinary Python ASGI and .NET API; isolated per-host state; no Worker",
              "dataset": {"profile": "P1", "source_class": "committed synthetic; 9477 payroll rows",
                          "seed_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()},
              "concurrency": 1, "pairs_per_route": 6, "warmup": "First post-readiness/setup read reported separately; next five warm reads retained.",
              "timing_boundary": "combined client HTTP send through bounded body parsing; excludes startup/setup/comparison",
              "token_connect_query_split": "unmeasured; no instrumentation supporting a reliable split",
              "cold_limit": "First read is not a cold OS, DNS, engine, token or capacity benchmark.",
              "network": "loopback, pooled warm HTTP, no live source/network; not a production speedup",
              "host_load": "Shared workstation; no other owned tests/builds/replays active. Other users and OS effects uncontrolled.",
              "slo": "not established; owner must agree acceptance/observation thresholds",
              "results": results, "live": "unmeasured: current capacity/access prerequisites unavailable"}
    target = ROOT / "dotnet" / "docs" / "integration-performance.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({case: row["summaries"] for case, row in results.items()}, indent=2))


if __name__ == "__main__":
    main()
