"""Generate `contract/scenarios/*.json` from the live route inventory plus the curated flows below.

Scenarios are DATA (the JSON this writes, reviewed by a person); this script is only how they are produced, so a route added to the
product shows up here as an uncovered route (`contract/COVERAGE.md`) instead of being silently absent.

    .\\contract\\py.ps1 -m contract.scenarios.build
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INVENTORY = json.loads((ROOT / "contract" / "inventory" / "routes.json").read_text(encoding="utf-8"))
OPENAPI = json.loads((ROOT / "contract" / "inventory" / "openapi.json").read_text(encoding="utf-8"))

CLIENT, YEAR, STATE, PROGRAM, UNIT = 1001, 2025, "GA", "GA_JTC", "GA_ATL_HQ"
LONG = "x" * 5000


def S(id: str, method: str, path: str, **kw: Any) -> dict[str, Any]:
    """One step. `kw`: query (list of pairs or dict), raw_query, json, body_text, body_b64, headers, capture, note."""
    request: dict[str, Any] = {"method": method, "path": path}
    for key in ("query", "raw_query", "json", "body_text", "body_b64", "form", "headers"):
        if key in kw:
            request[key] = kw.pop(key)
    step: dict[str, Any] = {"id": id, "request": request}
    for key in ("capture", "note", "requires"):
        if key in kw:
            step[key] = kw.pop(key)
    if kw:
        raise TypeError(f"unknown step option(s): {sorted(kw)}")
    return step


def C(id: str, op: str, **args: Any) -> dict[str, Any]:
    return {"id": id, "control": {"op": op, "args": args}}


def write(name: str, profile: str, steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    ids = [s["id"] for s in steps]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"{name}: duplicate step ids {sorted(dupes)}")
    scenario = {"name": name, "profile": profile, **extra, "steps": steps}
    (HERE / f"{name}.json").write_text(json.dumps(scenario, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return scenario


# ---------------------------------------------------------------------------------------------------------------------------
# Known-good values for every path parameter and a good request per route
# ---------------------------------------------------------------------------------------------------------------------------
PATH_VALUES = {
    "client_id": CLIENT, "account_id": CLIENT, "tax_year": YEAR, "state": STATE, "program_code": PROGRAM, "code": PROGRAM,
    "unit_id": UNIT, "employee_id": "{{employee_id}}", "record_token": "{{token}}", "finding_id": "{{finding_id}}",
    "exception_id": "{{exception_id}}", "draft_id": "{{draft_id}}", "batch_id": "{{batch_id}}", "artifact_id": "{{artifact_id}}",
    "tool": "book_rank", "method": "min_max",
}
INT_PATH = {"client_id", "account_id", "tax_year"}

#: Query parameters that make the route answer (the route returns a 422 or a refusal without them).
GOOD_QUERY: dict[str, Any] = {
    "GET /api/eligibility/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/progress/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/proximity/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/onezero/matrix/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/onezero/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/onezero/{tax_year}/employee/{employee_id}": {"state": STATE, "account_id": CLIENT},
    "GET /api/forecast/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/performance/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/alerts/monthly/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/qc/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/ingestion/{tax_year}": {"state": STATE, "account_id": CLIENT},
    "GET /api/ingestion/{tax_year}/rows": {"state": STATE, "account_id": CLIENT, "limit": 3},
    "GET /api/simulate/portfolio/{tax_year}": {"state": STATE},
    "GET /api/v2/clients/{client_id}/units": {"year": YEAR, "limit": 3},
    "GET /api/v2/clients/{client_id}/units/{unit_id}": {"year": YEAR, "limit": 3},
    "GET /api/v2/clients/{client_id}/units/{unit_id}/rebase": {"base_year": 2024},
    "GET /api/v2/employees/{record_token}": {"client_id": CLIENT, "year": YEAR},
    "GET /api/audit/channel": {"user_oid": "00000000-0000-0000-0000-000000000001"},
    "POST /api/clients/{client_id}/packages": {"tax_year": YEAR},
    "GET /api/designations/{state}": {"tax_year": YEAR},
}

#: A body that is valid for the route (so its success and its idempotency can be recorded).
GOOD_BODY: dict[str, Any] = {
    "POST /api/capabilities/{tool}": {"args": {}},
    "POST /api/chat": {"message": "Who should we call first?"},
    "POST /api/claims": {"client_id": CLIENT, "program_code": PROGRAM, "tax_year": 2023, "status": "claimed", "provenance": "client_asserted", "decided_by": "contract", "claimed_usd": "12000"},
    "POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition": {"status": "proposed", "decided_by": "contract"},
    "PUT /api/claims/engagement": {"client_id": CLIENT, "program_code": PROGRAM, "scope": "in_scope", "note": "contract"},
    "POST /api/claims/assess": {"client_id": CLIENT, "program_code": PROGRAM, "tax_years": [YEAR], "assessed_by": "contract"},
    "POST /api/rules/{code}/verify": {"verified_by": "contract", "note": "n"},
    "POST /api/onezero/employee/{employee_id}/review": {"status": "validated", "note": "n", "reviewer": "contract"},
    "POST /api/rules/ingested/{state}/apply": {"tax_year": YEAR, "confirmed_by": "contract"},
    "POST /api/simulate/unit": {"client_id": CLIENT, "worksite_id": UNIT, "tax_year": YEAR, "state": STATE, "action": "add_headcount", "magnitude": 2},
    "POST /api/simulate/employee": {"client_id": CLIENT, "tax_year": YEAR, "state": STATE, "employees": [{"record_token": "{{token}}", "additional_weekly_hours": 4, "hourly_raise": 1.5}]},
    "POST /api/simulate/onezero": {"tax_year": YEAR, "state": STATE, "client_id": CLIENT, "action": "add_headcount", "magnitude": 2},
    "POST /api/summary": {"page": "portfolio"},
    "POST /api/ingestion/{tax_year}/exceptions/{exception_id}/resolve": {"resolution": "accept", "reviewer": "contract"},
    "POST /api/findings/{finding_id}/resolve": {"client_id": CLIENT, "tax_year": YEAR, "resolution": "accept", "decided_by": "contract"},
    "POST /api/findings/{finding_id}/reopen": {"client_id": CLIENT, "tax_year": YEAR, "resolution": "accept", "decided_by": "contract"},
    "POST /api/v2/program-drafts": {"code": "XX_CONTRACT", "name": "Contract draft", "state": "XX", "years": [2025], "actor": "contract"},
    "PUT /api/v2/program-drafts/{draft_id}/documents": {"expected_version": 1, "name": "Contract draft", "actor": "contract", "years": {}},
    "POST /api/v2/program-drafts/{draft_id}/validate": {"actor": "contract"},
    "POST /api/v2/program-drafts/{draft_id}/request-review": {"actor": "contract"},
    "POST /api/v2/program-drafts/{draft_id}/review": {"decision": "request_changes", "comment": "c", "actor": "reviewer"},
    "POST /api/v2/program-drafts/{draft_id}/preview": {"dataset": "synthetic_sample"},
    "POST /api/v2/program-drafts/{draft_id}/withdraw": {"reason": "r", "actor": "contract"},
    "POST /api/v2/program-drafts/{draft_id}/export": {"write_local": False, "actor": "contract"},
    "POST /api/v2/run-batches": {"kind": "assess", "scope": {"kind": "one", "client_ids": [CLIENT]}, "tax_years": [YEAR], "dry_run": True},
    "POST /api/v2/clients/{client_id}/units/{unit_id}/base-year": {"base_year": 2024, "state": STATE, "justification": "contract", "triggered_by": "contract"},
    "POST /api/v2/clients/{client_id}/runs": {"year": YEAR, "state": STATE, "triggered_by": "contract"},
    "POST /api/employee/drill": {"record_token": "{{token}}", "tax_year": YEAR, "state": STATE, "account_id": CLIENT},
    "POST /api/workspace/source/search": {"q": "", "limit": 5, "offset": 0},
    "POST /api/workspace/eligibility/search": {"q": "", "limit": 5, "offset": 0, "status": "all", "proximity": "all"},
    "POST /api/workspace/employee": {"record_token": "{{token}}"},
    "POST /api/workspace/onezero/contributors": {"method": "min_max", "unit_id": UNIT, "fein": "58-1234567", "month_index": 0},
    "POST /api/workspace/comparison/stage": {"stage": "common_employee_totals"},
}


def api_routes() -> list[dict[str, Any]]:
    return [r for r in INVENTORY["routes"] if "framework_route" not in r]


def key(route: dict[str, Any]) -> str:
    return f"{route['method']} {route['path']}"


def fill(path: str, overrides: dict[str, Any] | None = None) -> str:
    values = {**PATH_VALUES, **(overrides or {})}
    return re.sub(r"\{(\w+)\}", lambda m: str(values[m.group(1)]), path)


def good_request(route: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {"method": route["method"], "path": fill(route["path"])}
    query = GOOD_QUERY.get(key(route))
    if query:
        request["query"] = [[k, v] for k, v in query.items()]
    body = GOOD_BODY.get(key(route))
    if body is not None:
        request["json"] = body
    return request


# ---------------------------------------------------------------------------------------------------------------------------
# Body schema walking: invalid inputs derived from the OpenAPI body schema, so every body route gets the same battery
# ---------------------------------------------------------------------------------------------------------------------------
def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = OPENAPI["components"]["schemas"][schema["$ref"].split("/")[-1]]
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            if option.get("type") != "null":
                return _resolve(option)
    return schema


def body_schema(route: dict[str, Any]) -> dict[str, Any] | None:
    content = route.get("request_body_schema") or {}
    schema = (content.get("application/json") or {}).get("schema")
    return _resolve(schema) if schema else None


def invalid_bodies(route: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Cases every body route is put through. Each is `(id suffix, step kwargs)`."""
    schema = body_schema(route) or {}
    props = schema.get("properties") or {}
    required = [r for r in schema.get("required") or [] if r in props]
    cases: list[tuple[str, dict[str, Any]]] = [
        ("empty-body", {}),
        ("not-json", {"body_text": "{not json", "headers": {"content-type": "application/json"}}),
        ("json-array", {"json": []}),
        ("json-string", {"json": "text"}),
        ("json-null", {"json": None}),
        ("empty-object", {"json": {}}),
        ("wrong-content-type", {"body_text": "a=b", "headers": {"content-type": "text/plain"}}),
    ]
    good = GOOD_BODY.get(key(route))
    if isinstance(good, dict):
        for name, prop in props.items():
            if name in good:
                kind = _resolve(prop).get("type")
                bad = {"integer": "abc", "number": "abc", "string": {"nested": True}, "boolean": "maybe", "array": "abc", "object": "abc"}.get(kind)
                if bad is not None:
                    cases.append((f"wrong-type-{name}", {"json": {**good, name: bad}}))
                    break
        for name in required[:1]:
            cases.append((f"missing-{name}", {"json": {k: v for k, v in good.items() if k != name}}))
        first_string = next((n for n, p in props.items() if _resolve(p).get("type") == "string" and n in good), None)
        if first_string:
            cases.append((f"long-string-{first_string}", {"json": {**good, first_string: LONG}}))
            cases.append((f"unicode-{first_string}", {"json": {**good, first_string: "Zoë \u2603 \U0001f600 \u202eRTL \"q\" \\ \t"}}))
    return cases


def query_types(route: dict[str, Any]) -> list[tuple[str, str]]:
    """(name, annotation) of the numeric query parameters, for `abc`, negative and huge values."""
    out = []
    for p in route.get("parameters", {}).get("query", []):
        ann = p["annotation"]
        if re.search(r"\bint\b|\bfloat\b", ann):
            out.append((p["name"], ann))
    return out


def variants(route: dict[str, Any], *, include_writes: bool) -> list[dict[str, Any]]:
    """The battery of non-success requests for one route."""
    k = key(route)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{route['method']}-{route['path']}".lower()).strip("-")
    good = good_request(route)
    steps: list[dict[str, Any]] = []

    def add(suffix: str, **req: Any) -> None:
        base = {kk: vv for kk, vv in good.items() if kk not in ("json",)}
        base.update(req)
        steps.append({"id": f"{slug}.{suffix}", "request": base})

    for name in route.get("parameters", {}).get("path", []):
        if name["name"] in INT_PATH:
            add(f"path-{name['name']}-abc", path=fill(route["path"], {name["name"]: "abc"}))
    for name, _ann in query_types(route):
        for label, value in (("abc", "abc"), ("negative", "-1"), ("zero", "0"), ("huge", "999999999")):
            if name == "magnitude" and label == "huge":
                continue  # FINDING F-1: magnitude=999999999 never returns (CPU-bound); see contract/FINDINGS.md
            base_q = [q for q in good.get("query", []) if q[0] != name]
            add(f"query-{name}-{label}", query=base_q + [[name, value]])
    add("unknown-query", query=good.get("query", []) + [["zz_unknown", "1"]])
    if route["method"] == "GET":
        add("trailing-slash", path=good["path"] + "/")
        add("head", method="HEAD")
        add("options", method="OPTIONS")
        add("wrong-method-post", method="POST", json={})
    else:
        other = "GET" if route["method"] != "GET" else "POST"
        add("wrong-method-get", method=other)
        add("wrong-method-delete", method="DELETE")
    if include_writes and k in GOOD_BODY:
        for suffix, kw in invalid_bodies(route):
            step_req = {"method": route["method"], "path": good["path"]}
            if "query" in good:
                step_req["query"] = good["query"]
            step_req.update(kw)
            steps.append({"id": f"{slug}.body-{suffix}", "request": step_req})
    return steps


def main() -> int:
    from contract.scenarios import flows

    flows.build_all(sys.modules[__name__])
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
