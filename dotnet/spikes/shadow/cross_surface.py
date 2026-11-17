"""Canonical fact projections across real local HTTP transports; no model or confirmation."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import json

from admission import ROOT
from hermetic import artifact_directory, host
from safe_compare import compare_responses

TOOLS = ("book_rank", "client_situation", "client_eligibility")


def canonical_response(value: object, status: int = 200) -> dict:
    return {"status": status, "headers": {}, "body": {"kind": "json", "value": value}}


async def observe(api: str, gateway: str) -> list:
    import httpx
    from contract import exchange

    rest = json.loads((ROOT / "contract" / "scenarios" / "g1_rest.json").read_text())
    mcp = json.loads((ROOT / "contract" / "scenarios" / "g1_mcp.json").read_text())
    mcp["steps"] = [step for step in mcp["steps"] if step["id"] in
                   {"initialize", "initialized-notification", *("call." + tool + ".typical" for tool in TOOLS)}]
    mcp["tokens"] = {"user": mcp["tokens"]["user"]}
    results = []
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        user = (await client.post(gateway + "/__contract__/mint", json=rest["tokens"]["user"])).json()["token"]
        principal = json.loads((ROOT / "contract" / "scenarios" / "p1_auth.json").read_text())["tokens"]["reader"]
        api_user = (await client.post(api + "/__contract__/mint", json=principal)).json()["token"]
        api_headers = {"Authorization": "Bearer " + api_user}
        async with httpx.AsyncClient(base_url=gateway, timeout=30, trust_env=False) as channel:
            mcp_rows = {row["id"]: row for row in await exchange.run_scenario(channel, mcp)}
            for ordinal, tool in enumerate(TOOLS, 1):
                step = deepcopy(next(s for s in rest["steps"] if s["id"] == "tool." + tool + ".typical"))
                step["request"]["headers"] = {"authorization": "Bearer {{token.user}}"}
                rest_row = await exchange.run_step(channel, step, {"token.user": user})
                api_reply = await client.post(api + "/api/capabilities/" + tool,
                                              json=step["request"]["json"], headers=api_headers)
                api_body = exchange.describe_body(api_reply.headers, api_reply.content)["value"]
                rest_body = rest_row["response"]["body"]["value"]
                mcp_body = mcp_rows["call." + tool + ".typical"]["response"]["body"]["value"]
                facts = [api_body.get("facts"), rest_body.get("facts"),
                         mcp_body.get("result", {}).get("structuredContent", {}).get("facts")]
                statuses = (rest_row["response"]["status"],
                            mcp_rows["call." + tool + ".typical"]["response"]["status"])
                for surface, value, status in zip(("rest", "mcp"), facts[1:], statuses):
                    verdict = compare_responses("canonical", canonical_response(facts[0], api_reply.status_code),
                                                 canonical_response(value, status), ordinal)
                    verdict.update(tool=tool, surface=surface, projection="complete canonical facts, not wire envelopes",
                                   available=all(isinstance(fact, dict) and fact for fact in facts))
                    results.append(verdict)
                if tool == "client_situation":
                    page = await client.get(api + "/api/v2/clients/1001/situation", headers=api_headers)
                    page_value = exchange.describe_body(page.headers, page.content)["value"]
                    verdict = compare_responses("situation", canonical_response(page_value, page.status_code),
                                                 canonical_response(facts[0], api_reply.status_code), ordinal)
                    verdict.update(tool=tool, surface="page-to-capability", available=bool(facts[0]),
                                   projection="complete client situation, no field subtraction")
                    results.append(verdict)
    return results


def main() -> None:
    from contract.replay_setup import prepare_external

    output = artifact_directory("cross-surface")
    with ExitStack() as stack:
        api, _ = stack.enter_context(host("api", output / "api"))
        gateway, _ = stack.enter_context(host("gateway", output / "gateway", "G1"))
        prepare_external(api, api + "/__contract__/reset",
                         {"profile": "P1", "auth": {"rate_limit_per_minute": 1000}})
        prepare_external(gateway, gateway + "/__contract__/reset", {"profile": "G1"})
        results = asyncio.run(observe(api, gateway))
    report = {"classification": "isolated synthetic; mandatory gateway audit retained",
              "product_revision": "006760b", "planned": len(TOOLS) * 2 + 1, "attempted": len(results),
              "matched": sum(row["semantic_equal"] and row["available"] for row in results),
              "topology": "separate API and standalone gateway hosts; gateway composes application in-process, no API dependency/listener",
              "caller": "same synthetic delegated person; host-specific validated audiences/scopes",
              "scope": "P1/G1 seed equivalence; full facts for three tools, not all capabilities or private data",
              "orchestrator": "Existing 39 scripted records and final Orchestrator.Tests gate; no live model/confirmation",
              "results": results}
    (ROOT / "dotnet" / "docs" / "integration-cross-surface.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"planned": report["planned"], "attempted": report["attempted"], "matched": report["matched"]}))


if __name__ == "__main__":
    main()
