"""Generate the host's decided route surface without importing the Python product."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def group(route: dict) -> str:
    path = route["path"]
    endpoint = route.get("endpoint", "")
    module = endpoint.rsplit(".", 1)[0]
    if route.get("framework_route") or module == "main":
        return "framework"
    if path.startswith("/api/workspace"):
        return "workspace_sealed"
    if module in {"api.chat", "api.summary", "api.capabilities"}:
        return "ai"
    if module in {"api.program_drafts", "api.programs", "api.run_batches"}:
        return "drafts_runs"
    if module == "api.trend" and any(
        term in path for term in ("/runs", "/base-year", "/rebase")
    ):
        return "drafts_runs"
    if module in {
        "api.claims", "api.findings", "api.artifacts", "api.rules",
        "api.rules_ingestion", "api.audit",
    }:
        return "claims_artifacts_rules"
    if module in {
        "api.scope", "api.trend", "api.eligibility", "api.onezero",
        "api.proximity", "api.forecast", "api.simulate", "api.retroactive",
        "api.ingestion", "api.auth",
    }:
        return "reads_calc"
    raise ValueError(f"Unassigned route: {route}")


def outputs(root: Path) -> dict[Path, str]:
    inventory = json.loads((root / "contract/inventory/routes.json").read_text())
    openapi = json.loads((root / "contract/inventory/openapi.json").read_text())
    channel = json.loads((root / "contract/inventory/channel.json").read_text())
    routes = []
    groups = {key: [] for key in (
        "framework", "reads_calc", "claims_artifacts_rules", "drafts_runs",
        "ai", "workspace_sealed", "gateway",
    )}
    for source in inventory["routes"]:
        methods = source["method"]
        for method in methods if isinstance(methods, list) else [methods]:
            operation = openapi["paths"].get(source["path"], {}).get(method.lower(), {})
            parameters = source.get("parameters", {})
            parameters = json.loads(json.dumps(parameters))
            for location, declared in parameters.items():
                for parameter in declared:
                    spec = next((p for p in operation.get("parameters", [])
                                 if p["in"] == location and p["name"] == parameter["name"]), {})
                    parameter["schema"] = spec.get("schema", {})
            route = {
                "method": method, "path": source["path"], "name": source["name"],
                "endpoint": source.get("endpoint", "framework." + source["name"]),
                "typed": not source["untyped"], "group": group(source),
                "parameters": parameters,
                "request_body_schema": source.get("request_body_schema", {}),
                "body_required": operation.get("requestBody", {}).get("required", False),
            }
            routes.append(route)
            groups[route["group"]].append(f"{method} {route['path']}")
    for source in channel["gateway_routes"]:
        for method in source["methods"]:
            routes.append({
                "method": method, "path": source["path"], "name": source["name"],
                "endpoint": "gateway." + source["name"], "typed": False,
                "group": "gateway", "parameters": {}, "request_body_schema": {},
                "body_required": False,
            })
            groups["gateway"].append(f"{method} {source['path']}")
    api = root / "dotnet/src/TaxCredit.Api/Contract"
    documents = {
        api / "routes.generated.json": {"routes": routes, "schemas": openapi["components"]["schemas"]},
        api / "openapi.generated.json": openapi,
        root / "dotnet/docs/route-groups.json": {"groups": groups},
    }
    return {path: json.dumps(value, indent=2, ensure_ascii=False) + "\n"
            for path, value in documents.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    for path, text in outputs(root).items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit(f"Registry drift: {path.relative_to(root)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
