"""The scenario set. Curated flows plus the generated battery from `build.py`."""
from __future__ import annotations

import json
from typing import Any

#: Captured at the start of every scenario that needs ids the data decides (a token is a hash of the employee, not a guess).
BOOT_P1 = [
    {"id": "boot.unit", "note": "capture an employee token and id from the unit drill",
     "request": {"method": "GET", "path": "/api/v2/clients/1001/units/GA_ATL_HQ", "query": [["year", 2025], ["limit", 2]]},
     "capture": {"token": "body.employees.0.record_token", "employee_id": "body.employees.0.employee_id"}},
    {"id": "boot.findings", "note": "capture a finding id",
     "request": {"method": "GET", "path": "/api/findings/1001/2025"},
     "capture": {"finding_id": "body.findings.0.finding_id"}},
]
VARS_P1 = {"exception_id": "t2:E00200:2025-02", "draft_id": "00000000-0000-0000-0000-00000000dead", "batch_id": "00000000-0000-0000-0000-00000000beef",
           "artifact_id": "00000000-0000-0000-0000-00000000cafe"}


def build_all(b: Any) -> None:
    S, C, write = b.S, b.C, b.write
    routes = b.api_routes()
    gets = [r for r in routes if r["method"] == "GET"]
    index = {b.key(r): r for r in routes}
    made: list[dict[str, Any]] = []

    # ------------------------------------------------------------------------------------------------ P1 reads
    steps: list[dict[str, Any]] = list(BOOT_P1)
    for r in gets:
        slug = b.re.sub(r"[^a-z0-9]+", "-", r["path"].lower()).strip("-")
        steps.append({"id": f"ok.{slug}", "request": b.good_request(r)})
    steps += [
        S("framework.openapi", "GET", "/openapi.json"), S("framework.docs", "GET", "/docs"), S("framework.redoc", "GET", "/redoc"),
        S("framework.oauth2-redirect", "GET", "/docs/oauth2-redirect"),
        S("404.unknown-path", "GET", "/api/nope"), S("404.root", "GET", "/"), S("404.api-root", "GET", "/api"),
        S("404.unknown-path-post", "POST", "/api/nope", json={}),
        S("405.health-post", "POST", "/api/health", json={}), S("405.health-delete", "DELETE", "/api/health"),
        S("405.health-put", "PUT", "/api/health", json={}), S("405.health-patch", "PATCH", "/api/health", json={}),
        S("trailing.health", "GET", "/api/health/"), S("trailing.double-slash", "GET", "//api/health"),
        S("case.path-uppercase", "GET", "/API/health"), S("head.health", "HEAD", "/api/health"),
        S("options.health", "OPTIONS", "/api/health"),
        S("cors.preflight", "OPTIONS", "/api/claims", headers={"origin": "https://example.test", "access-control-request-method": "POST", "access-control-request-headers": "content-type,authorization"}),
        S("cors.simple", "GET", "/api/health", headers={"origin": "https://example.test"}),
        S("cors.preflight-disallowed-method", "OPTIONS", "/api/claims", headers={"origin": "https://example.test", "access-control-request-method": "DELETE"}),
    ]
    for r in gets:
        steps += b.variants(r, include_writes=False)
    made.append(write("p1_reads", "P1", steps, variables=VARS_P1))

    # ------------------------------------------------------------------------------------------------ P1 query edges
    edge: list[dict[str, Any]] = list(BOOT_P1)
    P = "/api/v2/portfolio"
    for sid, q in [
        ("default", []), ("year", [["year", 2025]]), ("year-none", [["year", 1999]]), ("sort-priority-desc", [["sort", "priority"], ["order", "desc"]]),
        ("sort-identified", [["sort", "identified"], ["order", "desc"]]), ("sort-bogus", [["sort", "bogus"]]), ("order-bogus", [["order", "sideways"]]),
        ("limit-0", [["limit", 0]]), ("limit-1", [["limit", 1]]), ("limit-over-max", [["limit", 100000]]), ("limit-neg", [["limit", -5]]),
        ("offset-past-end", [["offset", 999]]), ("offset-neg", [["offset", -1]]), ("limit-abc", [["limit", "abc"]]), ("limit-float", [["limit", "1.5"]]),
        ("limit-empty", [["limit", ""]]), ("repeated-limit", [["limit", 1], ["limit", 2]]), ("repeated-status", [["status", "assessed"], ["status", "claimed"]]),
        ("status-bogus", [["status", "bogus"]]), ("near-true", [["near", "true"]]), ("near-bogus", [["near", "maybe"]]),
        ("program", [["program", "GA_JTC"]]), ("program-unknown", [["program", "ZZ_NONE"]]), ("scope", [["scope", "all"]]),
        ("outcome", [["outcome", "unclaimed"]]), ("unicode-query", [["program", "Zoë\u2603"]]), ("long-query", [["program", "x" * 5000]]),
        ("encoded-plus", [["program", "a+b c%20d"]]),
    ]:
        edge.append(S(f"portfolio.{sid}", "GET", P, query=q))
    edge.append(S("portfolio.raw-query-dupe-keys", "GET", P, raw_query="limit=1&limit=2&&=x&flag&year=2025"))
    for sid, q in [("limit-0", [["limit", 0]]), ("limit-1", [["limit", 1], ["offset", 1]]), ("offset-past-end", [["offset", 99999]]), ("limit-over-max", [["limit", 1000000]]),
                   ("sort-employee-desc", [["sort", "employee"], ["order", "desc"]]), ("q-unicode", [["q", "Zoë"]]), ("status-both", [["status", "both"]]), ("near-floor", [["near_floor", "true"]])]:
        edge.append(S(f"eligibility.{sid}", "GET", "/api/eligibility/2025", query=[["state", "GA"], ["account_id", 1001]] + q))
    for sid, q in [("limit-1", [["limit", 1]]), ("offset-past-end", [["offset", 99999]]), ("sort-bogus", [["sort", "bogus"]]), ("filter-bad", [["filter", "~"]]), ("filter-good", [["filter", "avg_weekly_hours:>=30"]]),
                   ("month-0", [["month", 0]]), ("month-13", [["month", 13]]), ("month-3", [["month", 3]]), ("near-min-hours", [["near_min_hours", 5]])]:
        edge.append(S(f"unit.{sid}", "GET", "/api/v2/clients/1001/units/GA_ATL_HQ", query=[["year", 2025]] + q))
    for sid, q in [("limit-1", [["limit", 1]]), ("offset-past-end", [["offset", 99999]]), ("year-none", [["year", 1999]]), ("state-bogus", [["state", "ZZ"]]), ("method-bogus", [["method", "bogus"]]), ("method-pp", [["method", "pay_period"]])]:
        edge.append(S(f"units.{sid}", "GET", "/api/v2/clients/1001/units", query=q))
    for sid, path in [("client-unknown", "/api/v2/clients/999999/units"), ("client-zero", "/api/v2/clients/0/units"), ("client-negative", "/api/v2/clients/-1/units"), ("client-huge", "/api/v2/clients/99999999999999999999/units"),
                      ("coverage-unknown", "/api/claims/coverage/999999"), ("cell-unknown", "/api/claims/cell/1001/ZZ_NONE/2025"), ("scope-unknown", "/api/scope/client/999999"),
                      ("situation-unknown", "/api/v2/clients/999999/situation"), ("employee-unknown-token", "/api/v2/employees/not-a-real-token-1234"),
                      ("program-unknown", "/api/v2/programs/ZZ_NONE"), ("draft-unknown", "/api/v2/program-drafts/00000000-0000-0000-0000-000000000000"),
                      ("batch-unknown", "/api/v2/run-batches/00000000-0000-0000-0000-000000000000"), ("batch-bad-id", "/api/v2/run-batches/not-a-uuid"),
                      ("rules-ingested-unknown-state", "/api/rules/ingested/ZZ"), ("designations-unknown-state", "/api/designations/ZZ"),
                      ("year-future", "/api/eligibility/2099"), ("year-past", "/api/progress/1900")]:
        edge.append(S(f"unknown.{sid}", "GET", path, query=[["state", "GA"], ["account_id", 1001]] if "eligibility" in path or "progress" in path else []))
    made.append(write("p1_query_edges", "P1", edge, variables=VARS_P1))

    # ------------------------------------------------------------------------------------------------ P1 writes
    w: list[dict[str, Any]] = list(BOOT_P1)
    for r in routes:
        if r["method"] in ("POST", "PUT") and "/program-drafts" not in r["path"] and "/run-batches" not in r["path"] and "/packages" not in r["path"] and "/capabilities" not in r["path"] and "/chat" not in r["path"] and "/summary" not in r["path"]:
            slug = b.re.sub(r"[^a-z0-9]+", "-", f"{r['method']}-{r['path']}".lower()).strip("-")
            w.append({"id": f"ok.{slug}", "request": b.good_request(r)})
    w += [
        S("claims.read-after", "GET", "/api/claims/coverage/1001"), S("claims.cell-after", "GET", "/api/claims/cell/1001/GA_JTC/2023"),
        S("claims.transition-declined-no-reason", "POST", "/api/claims/cell/1001/GA_JTC/2023/transition", json={"status": "declined", "decided_by": "contract"}),
        S("claims.transition-declined", "POST", "/api/claims/cell/1001/GA_JTC/2023/transition", json={"status": "declined", "decided_by": "contract", "decline_reason": "client chose not to"}),
        S("claims.transition-unknown-cell", "POST", "/api/claims/cell/1001/ZZ_NONE/2023/transition", json={"status": "claimed", "decided_by": "contract"}),
        S("claims.transition-bad-status", "POST", "/api/claims/cell/1001/GA_JTC/2023/transition", json={"status": "bogus"}),
        S("claims.create-duplicate", "POST", "/api/claims", json=b.GOOD_BODY["POST /api/claims"]),
        S("claims.create-money-as-number", "POST", "/api/claims", json={"client_id": 1001, "program_code": "GA_JTC", "tax_year": 2022, "status": "claimed", "provenance": "client_asserted", "claimed_usd": 1234.5}),
        S("claims.create-money-as-string", "POST", "/api/claims", json={"client_id": 1001, "program_code": "GA_JTC", "tax_year": 2021, "status": "claimed", "provenance": "client_asserted", "claimed_usd": "1234.50"}),
        S("claims.create-money-raw-exponent", "POST", "/api/claims", body_text='{"client_id":1001,"program_code":"GA_JTC","tax_year":2020,"status":"claimed","provenance":"client_asserted","claimed_usd":1e3}', headers={"content-type": "application/json"}),
        S("claims.create-unknown-client", "POST", "/api/claims", json={"client_id": 999999, "program_code": "GA_JTC", "tax_year": 2023, "status": "claimed", "provenance": "client_asserted"}),
        S("claims.create-bad-provenance", "POST", "/api/claims", json={"client_id": 1001, "program_code": "GA_JTC", "tax_year": 2023, "status": "claimed", "provenance": "bogus"}),
        S("claims.assess-unknown-client", "POST", "/api/claims/assess", json={"client_id": 999999, "assessed_by": "contract"}),
        S("claims.assess-blank-assessor", "POST", "/api/claims/assess", json={"client_id": 1001, "assessed_by": ""}),
        S("claims.engagement-bad-scope", "PUT", "/api/claims/engagement", json={"client_id": 1001, "program_code": "GA_JTC", "scope": "bogus"}),
        S("claims.coverage-final", "GET", "/api/claims/coverage"), S("claims.portfolio-final", "GET", "/api/v2/portfolio"),
        S("findings.resolve", "POST", "/api/findings/{{finding_id}}/resolve", json={"client_id": 1001, "tax_year": 2025, "resolution": "accept", "decided_by": "contract"}),
        S("findings.read-after-resolve", "GET", "/api/findings/1001/2025"),
        S("findings.history", "GET", "/api/findings/1001/{{finding_id}}/history"),
        S("findings.resolve-assign-without-site", "POST", "/api/findings/{{finding_id}}/resolve", json={"client_id": 1001, "tax_year": 2025, "resolution": "assign"}),
        S("findings.resolve-unknown", "POST", "/api/findings/does-not-exist/resolve", json={"client_id": 1001, "tax_year": 2025, "resolution": "accept"}),
        S("findings.reopen", "POST", "/api/findings/{{finding_id}}/reopen", json={"client_id": 1001, "tax_year": 2025, "resolution": "accept"}),
        S("findings.reopen-again", "POST", "/api/findings/{{finding_id}}/reopen", json={"client_id": 1001, "tax_year": 2025, "resolution": "accept"}),
        S("findings.history-unknown-client", "GET", "/api/findings/999999/x/history"),
        S("ingestion.resolve-reopen", "POST", "/api/ingestion/2025/exceptions/{{exception_id}}/resolve", json={"resolution": "reopen", "reviewer": "contract"}),
        S("ingestion.resolve-bogus", "POST", "/api/ingestion/2025/exceptions/{{exception_id}}/resolve", json={"resolution": "bogus"}),
        S("ingestion.resolve-unknown-exception", "POST", "/api/ingestion/2025/exceptions/zz:nope/resolve", json={"resolution": "accept", "reviewer": "contract"}),
        S("ingestion.read-after", "GET", "/api/ingestion/2025", query=[["state", "GA"], ["account_id", 1001]]),
        S("onezero.review-bogus-status", "POST", "/api/onezero/employee/{{employee_id}}/review", json={"status": "bogus"}),
        S("rules.verify-unknown", "POST", "/api/rules/ZZ_NONE/verify", json={"verified_by": "contract"}),
        S("rules.ingested-apply-unknown-state", "POST", "/api/rules/ingested/ZZ/apply", json={"tax_year": 2025}),
        S("rules.read-after-verify", "GET", "/api/rules"),
        S("baseyear.rebase-after", "GET", "/api/v2/clients/1001/units/GA_ATL_HQ/rebase", query=[["base_year", 2024]]),
        S("baseyear.unknown-unit", "POST", "/api/v2/clients/1001/units/ZZ_NONE/base-year", json={"base_year": 2024, "triggered_by": "contract"}),
        S("baseyear.year-null", "POST", "/api/v2/clients/1001/units/GA_ATL_HQ/base-year", json={"base_year": None, "triggered_by": "contract"}),
        S("runs.latest-after", "GET", "/api/v2/clients/1001/runs/latest"),
        S("runs.unknown-client", "POST", "/api/v2/clients/999999/runs", json={"year": 2025, "triggered_by": "contract"}),
        S("runs.future-year", "POST", "/api/v2/clients/1001/runs", json={"year": 2099, "triggered_by": "contract"}),
        S("drill.unknown-token", "POST", "/api/employee/drill", json={"record_token": "not-a-real-token", "tax_year": 2025}),
        S("simulate.unit-unknown-site", "POST", "/api/simulate/unit", json={"client_id": 1001, "worksite_id": "ZZ", "tax_year": 2025, "action": "add_headcount", "magnitude": 1}),
        S("simulate.unit-bad-hours", "POST", "/api/simulate/unit", json={"client_id": 1001, "worksite_id": "GA_ATL_HQ", "tax_year": 2025, "hire_weekly_hours": 81}),
        S("simulate.unit-zero-hours", "POST", "/api/simulate/unit", json={"client_id": 1001, "worksite_id": "GA_ATL_HQ", "tax_year": 2025, "hire_weekly_hours": 0}),
        S("simulate.unit-bad-action", "POST", "/api/simulate/unit", json={"client_id": 1001, "worksite_id": "GA_ATL_HQ", "tax_year": 2025, "action": "bogus"}),
        S("simulate.employee-empty", "POST", "/api/simulate/employee", json={"client_id": 1001, "tax_year": 2025, "employees": []}),
        S("simulate.onezero-negative", "POST", "/api/simulate/onezero", json={"tax_year": 2025, "state": "GA", "client_id": 1001, "action": "remove_headcount", "magnitude": -3}),
        S("simulate.portfolio-bad-action", "GET", "/api/simulate/portfolio/2025", query=[["state", "GA"], ["action", "bogus"]]),
        S("simulate.portfolio-magnitude-abc", "GET", "/api/simulate/portfolio/2025", query=[["state", "GA"], ["magnitude", "abc"]]),
    ]
    for r in routes:
        if r["method"] in ("POST", "PUT") and b.key(r) in b.GOOD_BODY and not any(s in r["path"] for s in ("/program-drafts", "/run-batches", "/packages", "/capabilities", "/chat", "/summary")):
            w += b.variants(r, include_writes=True)
    made.append(write("p1_writes", "P1", w, variables=VARS_P1))

    # ------------------------------------------------------------------------------------------------ P1 program drafts
    from tests import draft_world as dw

    docs = dw.documents()
    docs_one = dw.documents((2025,))
    D = "/api/v2/program-drafts"
    d: list[dict[str, Any]] = [
        C("env.second-reviewer", "env", set={"PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER": "true"}),
        S("create", "POST", D, json={"code": dw.CODE, "name": "Zedland Two Jobs Credit", "state": dw.STATE, "years": [2024, 2025], "actor": "ann"}, capture={"draft_id": "body.draft_id", "version": "body.version"}),
        S("create-duplicate-code", "POST", D, json={"code": dw.CODE, "name": "Again", "state": dw.STATE, "years": [2025], "actor": "ann"}),
        S("create-bad-code", "POST", D, json={"code": "bad code!", "name": "x", "state": "ZZ", "years": [2025]}),
        S("create-long-code", "POST", D, json={"code": "X" * 65, "name": "x", "state": "ZZ"}),
        S("get", "GET", f"{D}/{{{{draft_id}}}}"), S("list", "GET", D), S("list-status", "GET", D, query=[["status", "draft"]]),
        S("list-status-bogus", "GET", D, query=[["status", "bogus"]]), S("list-limit-0", "GET", D, query=[["limit", 0]]), S("list-offset-past", "GET", D, query=[["offset", 99]]),
        S("validate-empty-scaffold", "POST", f"{D}/{{{{draft_id}}}}/validate", json={"actor": "ann"}, capture={"version": "body.version"}),
        S("request-review-while-invalid", "POST", f"{D}/{{{{draft_id}}}}/request-review", json={"actor": "ann"}),
        S("documents-stale-version", "PUT", f"{D}/{{{{draft_id}}}}/documents", json={"expected_version": 999, "pack": docs["pack"], "years": docs["years"], "actor": "ann"}),
        S("documents-wrong-code", "PUT", f"{D}/{{{{draft_id}}}}/documents", json={"expected_version": "{{version}}", "pack": {**docs["pack"], "credit": {**docs["pack"]["credit"], "code": "ZZ_OTHER"}}, "years": docs["years"], "actor": "ann"}, capture={"version": "body.version"}),
        S("documents-fill", "PUT", f"{D}/{{{{draft_id}}}}/documents", json={"expected_version": "{{version}}", "pack": docs["pack"], "years": docs["years"], "actor": "ann"}, capture={"version": "body.version"}),
        S("documents-oversize-note", "PUT", f"{D}/{{{{draft_id}}}}/documents", json={"expected_version": "{{version}}", "pack": {**docs["pack"], "_note": "x" * 9000}, "years": docs["years"], "actor": "ann"}),
        S("validate", "POST", f"{D}/{{{{draft_id}}}}/validate", json={"actor": "ann"}, capture={"version": "body.version"}),
        S("validate-null-body", "POST", f"{D}/{{{{draft_id}}}}/validate", body_text="null", headers={"content-type": "application/json"}),
        S("validate-no-body", "POST", f"{D}/{{{{draft_id}}}}/validate"),
        S("preview-synthetic", "POST", f"{D}/{{{{draft_id}}}}/preview", json={"dataset": "synthetic_sample"}),
        S("preview-client-refused", "POST", f"{D}/{{{{draft_id}}}}/preview", json={"dataset": "client", "client_id": 1001, "tax_years": [2025]}),
        S("preview-bad-dataset", "POST", f"{D}/{{{{draft_id}}}}/preview", json={"dataset": "bogus"}),
        S("export-before-approval", "POST", f"{D}/{{{{draft_id}}}}/export", json={"write_local": False, "actor": "ann"}),
        S("manifest-before-export", "GET", f"{D}/{{{{draft_id}}}}/export/manifest"),
        S("review-before-request", "POST", f"{D}/{{{{draft_id}}}}/review", json={"decision": "approve", "actor": "bob"}),
        S("request-review", "POST", f"{D}/{{{{draft_id}}}}/request-review", json={"actor": "ann"}),
        S("review-self-approve", "POST", f"{D}/{{{{draft_id}}}}/review", json={"decision": "approve", "actor": "ann"}),
        S("review-bad-decision", "POST", f"{D}/{{{{draft_id}}}}/review", json={"decision": "bogus", "actor": "bob"}),
        S("review-long-comment", "POST", f"{D}/{{{{draft_id}}}}/review", json={"decision": "request_changes", "comment": "c" * 2001, "actor": "bob"}),
        S("review-request-changes", "POST", f"{D}/{{{{draft_id}}}}/review", json={"decision": "request_changes", "comment": "needs a citation", "actor": "bob"}),
        S("documents-after-changes", "PUT", f"{D}/{{{{draft_id}}}}/documents", json={"expected_version": 999, "pack": docs["pack"], "years": docs["years"], "actor": "ann"}),
        S("get-after-changes", "GET", f"{D}/{{{{draft_id}}}}"),
        S("withdraw", "POST", f"{D}/{{{{draft_id}}}}/withdraw", json={"reason": "superseded", "actor": "ann"}),
        S("withdraw-again", "POST", f"{D}/{{{{draft_id}}}}/withdraw", json={"reason": "again", "actor": "ann"}),
        S("get-withdrawn", "GET", f"{D}/{{{{draft_id}}}}"),
        S("second-create", "POST", D, json={"code": dw.CODE, "name": "Zedland Two Jobs Credit", "state": dw.STATE, "years": [2024, 2025], "actor": "ann"}, capture={"draft2": "body.draft_id", "version2": "body.version"}),
        S("second-fill", "PUT", f"{D}/{{{{draft2}}}}/documents", json={"expected_version": "{{version2}}", "pack": docs["pack"], "years": docs["years"], "actor": "ann"}),
        S("second-validate", "POST", f"{D}/{{{{draft2}}}}/validate", json={"actor": "ann"}),
        S("second-request-review", "POST", f"{D}/{{{{draft2}}}}/request-review", json={"actor": "ann"}),
        S("second-approve", "POST", f"{D}/{{{{draft2}}}}/review", json={"decision": "approve", "actor": "bob", "comment": "ok"}),
        S("second-export", "POST", f"{D}/{{{{draft2}}}}/export", json={"write_local": False, "actor": "ann"}),
        S("second-export-write-local", "POST", f"{D}/{{{{draft2}}}}/export", json={"write_local": True, "actor": "ann"}),
        S("second-manifest", "GET", f"{D}/{{{{draft2}}}}/export/manifest"),
        S("list-final", "GET", D),
    ]
    for r in routes:
        if "/program-drafts" in r["path"]:
            d += [s for s in b.variants(r, include_writes=True)]
    made.append(write("p1_program_drafts", "P1", d, variables=VARS_P1))

    # ------------------------------------------------------------------------------------------------ P1 artifacts, capabilities, chat
    a: list[dict[str, Any]] = list(BOOT_P1) + [
        S("package.create", "POST", "/api/clients/1001/packages", query=[["tax_year", 2025]], capture={"artifact_id": "body.artifact_id"}),
        S("package.create-again", "POST", "/api/clients/1001/packages", query=[["tax_year", 2025]]),
        S("package.no-year", "POST", "/api/clients/1001/packages"), S("package.year-abc", "POST", "/api/clients/1001/packages", query=[["tax_year", "abc"]]),
        S("package.unknown-client", "POST", "/api/clients/999999/packages", query=[["tax_year", 2025]]),
        S("package.year-uncalculated", "POST", "/api/clients/1001/packages", query=[["tax_year", 2019]]),
        S("artifact.download", "GET", "/api/clients/1001/artifacts/{{artifact_id}}"),
        S("artifact.download-head", "HEAD", "/api/clients/1001/artifacts/{{artifact_id}}"),
        S("artifact.wrong-client", "GET", "/api/clients/999999/artifacts/{{artifact_id}}"),
        S("artifact.unknown", "GET", "/api/clients/1001/artifacts/00000000-0000-0000-0000-000000000000"),
        S("artifact.bad-id", "GET", "/api/clients/1001/artifacts/not-a-uuid"),
        S("capabilities.list", "GET", "/api/capabilities"),
        S("capabilities.unknown-tool", "POST", "/api/capabilities/no_such_tool", json={"args": {}}),
        S("capabilities.book-rank", "POST", "/api/capabilities/book_rank", json={"args": {}}),
        S("capabilities.book-rank-bad-arg", "POST", "/api/capabilities/book_rank", json={"args": {"limit": "abc"}}),
        S("capabilities.client-situation", "POST", "/api/capabilities/client_situation", json={"args": {"client_id": 1001}}),
        S("capabilities.client-situation-missing-arg", "POST", "/api/capabilities/client_situation", json={"args": {}}),
        S("capabilities.client-eligibility", "POST", "/api/capabilities/client_eligibility", json={"args": {"client_id": 1001, "tax_year": 2025}}),
        S("capabilities.args-not-object", "POST", "/api/capabilities/book_rank", json={"args": [1]}),
        S("capabilities.idempotency-key-too-long", "POST", "/api/capabilities/book_rank", json={"args": {}, "idempotency_key": "k" * 201}),
        S("capabilities.debug-tool", "POST", "/api/capabilities/channel_ping", json={"args": {}}),
        S("chat.ask", "POST", "/api/chat", json={"message": "Who should we call first?"}),
        S("chat.ask-client", "POST", "/api/chat", json={"message": "Give me a brief", "client_id": 1001, "tax_year": 2025, "state": "GA"}),
        S("chat.empty-message", "POST", "/api/chat", json={"message": ""}),
        S("chat.history", "POST", "/api/chat", json={"message": "and their trend?", "client_id": 1001, "history": [{"role": "user", "content": "brief"}]}),
        S("chat.bad-history", "POST", "/api/chat", json={"message": "x", "history": "abc"}),
        S("summary.portfolio", "POST", "/api/summary", json={"page": "portfolio"}),
        S("summary.client", "POST", "/api/summary", json={"page": "client", "client_id": 1001, "tax_year": 2025, "state": "GA"}),
        S("summary.unit", "POST", "/api/summary", json={"page": "unit", "client_id": 1001, "tax_year": 2025, "worksite_id": "GA_ATL_HQ"}),
        S("summary.employee", "POST", "/api/summary", json={"page": "employee", "client_id": 1001, "tax_year": 2025, "record_token": "{{token}}"}),
        S("summary.bad-page", "POST", "/api/summary", json={"page": "bogus"}),
        S("summary.client-without-client", "POST", "/api/summary", json={"page": "client"}),
        S("summary.short-token", "POST", "/api/summary", json={"page": "employee", "record_token": "short"}),
        S("summary.bad-month", "POST", "/api/summary", json={"page": "unit", "month": 13}),
    ]
    made.append(write("p1_artifacts_ai", "P1", a, variables=VARS_P1))

    # ------------------------------------------------------------------------------------------------ P1 workspace + unavailable dependency
    ws: list[dict[str, Any]] = list(BOOT_P1)
    for r in routes:
        if r["path"].startswith("/api/workspace"):
            ws.append({"id": "ok." + b.re.sub(r"[^a-z0-9]+", "-", f"{r['method']}-{r['path']}".lower()).strip("-"), "request": b.good_request(r)})
    ws += [
        S("onezero-contributors.bad-method", "POST", "/api/workspace/onezero/contributors", json={"method": "x", "unit_id": "u", "fein": "f", "month_index": 0}),
        S("onezero-contributors.month-12", "POST", "/api/workspace/onezero/contributors", json={"method": "min_max", "unit_id": "u", "fein": "f", "month_index": 12}),
        S("source-search.limit-201", "POST", "/api/workspace/source/search", json={"q": "", "limit": 201}),
        S("source-search.limit-0", "POST", "/api/workspace/source/search", json={"q": "", "limit": 0}),
        S("comparison-stage.bad", "POST", "/api/workspace/comparison/stage", json={"stage": "bogus"}),
        S("onezero-method.bad", "GET", "/api/workspace/onezero/bogus"),
        S("short-token", "POST", "/api/workspace/employee", json={"record_token": "x"}),
        C("env.lakehouse-unconfigured", "env", set={"DATA_SOURCE": "lakehouse"}, unset=["FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"]),
        S("unavailable.workspace", "GET", "/api/workspace"), S("unavailable.workspace-refresh", "POST", "/api/workspace/refresh"),
        S("unavailable.scope", "GET", "/api/scope"), S("unavailable.portfolio", "GET", "/api/v2/portfolio"),
        S("unavailable.units", "GET", "/api/v2/clients/1001/units", query=[["year", 2025]]),
        S("unavailable.eligibility", "GET", "/api/eligibility/2025", query=[["state", "GA"], ["account_id", 1001]]),
        S("unavailable.ingestion", "GET", "/api/ingestion/2025", query=[["state", "GA"], ["account_id", 1001]]),
        S("unavailable.forecast", "GET", "/api/forecast/2025", query=[["state", "GA"], ["account_id", 1001]]),
        S("unavailable.health-still-ok", "GET", "/api/health"),
    ]
    made.append(write("p1_workspace_unavailable", "P1", ws, variables=VARS_P1))

    # ------------------------------------------------------------------------------------------------ P2: multi-client
    p2: list[dict[str, Any]] = [
        {"id": "boot.unit", "request": {"method": "GET", "path": "/api/v2/clients/2001/units", "query": [["year", 2025], ["limit", 2]]}, "capture": {"unit": "body.items.0.worksite_id"}},
    ]
    for sid, q in [("default", []), ("year", [["year", 2025]]), ("sort-priority-desc", [["sort", "priority"], ["order", "desc"]]), ("sort-identified", [["sort", "identified"], ["order", "desc"]]),
                   ("limit-2-offset-1", [["limit", 2], ["offset", 1]]), ("near", [["near", "true"]]), ("status-assessed", [["status", "assessed"]]), ("program", [["program", "GA_JTC"]]),
                   ("limit-0", [["limit", 0]]), ("offset-past-end", [["offset", 99]]), ("scope-state", [["scope", "state:GA"]])]:
        p2.append(S(f"portfolio.{sid}", "GET", "/api/v2/portfolio", query=q))
    p2 += [S("scope", "GET", "/api/scope"), S("claims.coverage", "GET", "/api/claims/coverage"), S("claims.coverage-year", "GET", "/api/claims/coverage", query=[["tax_year", 2025]]),
           S("claims.lifecycle", "GET", "/api/claims/lifecycle"), S("me", "GET", "/api/me"), S("ready", "GET", "/api/ready"), S("health", "GET", "/api/health")]
    for cid in (2001, 2002, 2003, 2004):
        p2 += [S(f"client{cid}.scope", "GET", f"/api/scope/client/{cid}"), S(f"client{cid}.situation", "GET", f"/api/v2/clients/{cid}/situation"),
               S(f"client{cid}.coverage", "GET", f"/api/claims/coverage/{cid}"), S(f"client{cid}.units", "GET", f"/api/v2/clients/{cid}/units", query=[["year", 2025], ["limit", 5]]),
               S(f"client{cid}.units-pp", "GET", f"/api/v2/clients/{cid}/units", query=[["year", 2025], ["method", "pay_period"], ["limit", 5]]),
               S(f"client{cid}.run-latest", "GET", f"/api/v2/clients/{cid}/runs/latest"),
               S(f"client{cid}.eligibility", "GET", "/api/eligibility/2025", query=[["state", "GA"], ["account_id", cid], ["limit", 3]]),
               S(f"client{cid}.progress", "GET", "/api/progress/2025", query=[["state", "GA"], ["account_id", cid]]),
               S(f"client{cid}.proximity", "GET", "/api/proximity/2025", query=[["state", "GA"], ["account_id", cid]]),
               S(f"client{cid}.onezero-matrix", "GET", "/api/onezero/matrix/2025", query=[["state", "GA"], ["account_id", cid]]),
               S(f"client{cid}.forecast", "GET", "/api/forecast/2025", query=[["state", "GA"], ["account_id", cid]])]
    p2 += [S("client2001.unit-detail", "GET", "/api/v2/clients/2001/units/{{unit}}", query=[["year", 2025], ["limit", 3]]),
           S("client2001.unit-rebase", "GET", "/api/v2/clients/2001/units/{{unit}}/rebase", query=[["base_year", 2022]]),
           S("client2001.unit-other-client", "GET", "/api/v2/clients/2002/units/{{unit}}", query=[["year", 2025]]),
           S("client-nonexistent.units", "GET", "/api/v2/clients/3000/units", query=[["year", 2025]]),
           S("client-nonexistent.scope", "GET", "/api/scope/client/3000"), S("client-nonexistent.situation", "GET", "/api/v2/clients/3000/situation"),
           S("client2001.year-uncalculated", "GET", "/api/v2/clients/2001/units", query=[["year", 2019]]),
           S("client2001.claims-assess", "POST", "/api/claims/assess", json={"client_id": 2001, "assessed_by": "contract"}),
           S("client2002.run", "POST", "/api/v2/clients/2002/runs", json={"year": 2025, "state": "GA", "triggered_by": "contract"}),
           S("client2002.run-latest-after", "GET", "/api/v2/clients/2002/runs/latest"),
           S("portfolio.after-writes", "GET", "/api/v2/portfolio")]
    made.append(write("p2_reads_writes", "P2", p2))

    # ------------------------------------------------------------------------------------------------ P2: run batches
    R = "/api/v2/run-batches"
    one = {"kind": "assess", "scope": {"kind": "one", "client_ids": [2001]}, "tax_years": [2025]}
    rb: list[dict[str, Any]] = [
        S("list-empty", "GET", R),
        S("dry-run", "POST", R, json={**one, "dry_run": True}),
        S("dry-run-all", "POST", R, json={"kind": "assess_and_calculate", "scope": {"kind": "all"}, "dry_run": True}),
        S("dry-run-list", "POST", R, json={"kind": "calculate", "scope": {"kind": "list", "client_ids": [2001, 2002, 2003]}, "tax_years": [2025], "dry_run": True}),
        S("dry-run-filter", "POST", R, json={"kind": "assess", "scope": {"kind": "filter", "filter": {"state": "GA"}}, "dry_run": True}),
        S("create", "POST", R, json={**one, "idempotency_key": "contract-1"}, capture={"batch_id": "body.batch_id"}),
        S("create-replay", "POST", R, json={**one, "idempotency_key": "contract-1"}),
        S("create-same-key-different-body", "POST", R, json={"kind": "calculate", "scope": {"kind": "one", "client_ids": [2002]}, "tax_years": [2025], "idempotency_key": "contract-1"}),
        S("get-queued", "GET", f"{R}/{{{{batch_id}}}}"), S("items-queued", "GET", f"{R}/{{{{batch_id}}}}/items"),
        C("drain", "drain"),
        S("get-done", "GET", f"{R}/{{{{batch_id}}}}"), S("items-done", "GET", f"{R}/{{{{batch_id}}}}/items"),
        S("items-status", "GET", f"{R}/{{{{batch_id}}}}/items", query=[["status", "succeeded"]]), S("items-status-bogus", "GET", f"{R}/{{{{batch_id}}}}/items", query=[["status", "bogus"]]),
        S("items-limit-0", "GET", f"{R}/{{{{batch_id}}}}/items", query=[["limit", 0]]), S("items-offset-past", "GET", f"{R}/{{{{batch_id}}}}/items", query=[["offset", 99]]),
        S("cancel-finished", "POST", f"{R}/{{{{batch_id}}}}/cancel"), S("retry-nothing-failed", "POST", f"{R}/{{{{batch_id}}}}/retry-failed"),
        S("skip-unchanged", "POST", R, json={**one, "skip_unchanged": True, "idempotency_key": "contract-2"}, capture={"batch2": "body.batch_id"}),
        C("drain-2", "drain"), S("get-skip-unchanged", "GET", f"{R}/{{{{batch2}}}}"), S("items-skip-unchanged", "GET", f"{R}/{{{{batch2}}}}/items"),
        S("create-calculate-all", "POST", R, json={"kind": "assess_and_calculate", "scope": {"kind": "all"}, "tax_years": [2025], "idempotency_key": "contract-3", "confirm_items": 4, "force": True}, capture={"batch3": "body.batch_id"}),
        S("get-calculate-queued", "GET", f"{R}/{{{{batch3}}}}"),
        S("cancel-queued", "POST", f"{R}/{{{{batch3}}}}/cancel"), S("get-cancelled", "GET", f"{R}/{{{{batch3}}}}"), S("items-cancelled", "GET", f"{R}/{{{{batch3}}}}/items"),
        S("retry-after-cancel", "POST", f"{R}/{{{{batch3}}}}/retry-failed"),
        S("unknown-client", "POST", R, json={"kind": "assess", "scope": {"kind": "one", "client_ids": [999999]}, "dry_run": True}),
        S("empty-list", "POST", R, json={"kind": "assess", "scope": {"kind": "list", "client_ids": []}, "dry_run": True}),
        S("bad-kind", "POST", R, json={"kind": "bogus", "scope": {"kind": "one", "client_ids": [2001]}}),
        S("bad-scope-kind", "POST", R, json={"kind": "assess", "scope": {"kind": "bogus"}}),
        S("long-idempotency-key", "POST", R, json={**one, "idempotency_key": "k" * 129}),
        S("list-status", "GET", R, query=[["status", "succeeded"]]), S("list-status-bogus", "GET", R, query=[["status", "bogus"]]),
        S("list-after", "GET", R), S("list-limit-1", "GET", R, query=[["limit", 1]]), S("list-offset-past", "GET", R, query=[["offset", 99]]), S("list-limit-0", "GET", R, query=[["limit", 0]]),
        S("get-unknown", "GET", f"{R}/00000000-0000-0000-0000-000000000000"), S("cancel-unknown", "POST", f"{R}/00000000-0000-0000-0000-000000000000/cancel"),
        S("retry-unknown", "POST", f"{R}/00000000-0000-0000-0000-000000000000/retry-failed"), S("items-unknown", "GET", f"{R}/00000000-0000-0000-0000-000000000000/items"),
    ]
    for r in routes:
        if "/run-batches" in r["path"]:
            rb += [s for s in b.variants(r, include_writes=True) if "body-" in s["id"] or "wrong-method" in s["id"]]
    made.append(write("p2_run_batches", "P2", rb, variables={"batch_id": "00000000-0000-0000-0000-00000000beef"}))

    made.append(_auth(b))
    from contract.scenarios import flows_channel

    made += flows_channel.build_all(b)

    print(f"wrote {len(made)} scenarios, {sum(len(m['steps']) for m in made)} steps")


def _auth(b: Any) -> dict[str, Any]:
    """Stage C4: sign-in and policy. Tokens are minted at run time (`tokens` below); the recordings hold placeholders."""
    from application.acting_user import encode

    S, write = b.S, b.write
    tenant = "00000000-0000-0000-0000-0000000000aa"
    reader, writer = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000a2"

    def acting(oid: str, **kw: Any) -> str:
        return encode({"oid": oid, "tid": tenant, "name": "Acting Person", "upn": "acting@example.test", "channel": "teams", **kw})

    tokens = {
        "reader": {"kind": "user", "oid": reader}, "writer": {"kind": "user", "oid": writer},
        "restricted": {"kind": "user", "oid": "00000000-0000-0000-0000-0000000000a3"},
        "expired": {"exp_in": -7200}, "not_yet_valid": {"nbf_in": 7200}, "wrong_audience": {"aud": "api://some-other-api"},
        "wrong_tenant": {"iss": "https://login.microsoftonline.com/00000000-0000-0000-0000-0000000000ff/v2.0"},
        "wrong_issuer_v1": {"iss": f"https://sts.windows.net/{tenant}/"}, "forged": {"key": "other"},
        "no_scope": {"scp": "openid profile"}, "no_role": {"roles": []}, "wrong_role": {"roles": ["Reader"]},
        "user_with_agent_role": {"roles": ["TCC.User", "TCC.Agent"]}, "missing_exp": {"drop": ["exp"]}, "missing_iat": {"drop": ["iat"]},
        "bare_audience": {"aud": "11111111-2222-3333-4444-555555555555"},
        "agent": {"kind": "agent"}, "agent_with_scope": {"kind": "agent", "claims": {"scp": "user_impersonation"}},
        "agent_wrong_role": {"kind": "agent", "roles": ["TCC.User"]}, "agent_no_role": {"kind": "agent", "roles": []},
        "agent_named": {"kind": "agent", "claims": {"preferred_username": "x@example.test"}},
    }
    bearer = lambda name: {"authorization": f"Bearer {{{{token.{name}}}}}"}  # noqa: E731
    steps: list[dict[str, Any]] = []
    # --- no or malformed proof
    steps += [S("public.health-no-token", "GET", "/api/health"), S("public.ready-no-token", "GET", "/api/ready"), S("none.me", "GET", "/api/me"),
              S("none.portfolio", "GET", "/api/v2/portfolio"), S("none.post-claims", "POST", "/api/claims", json=b.GOOD_BODY["POST /api/claims"]),
              S("none.unknown-path", "GET", "/api/nope"), S("none.docs", "GET", "/docs"), S("none.openapi", "GET", "/openapi.json"),
              S("none.trailing-slash", "GET", "/api/me/"), S("none.options", "OPTIONS", "/api/me")]
    for sid, header in [("garbage", "Bearer garbage"), ("basic", "Basic dXNlcjpwYXNz"), ("empty-bearer", "Bearer"), ("no-scheme", "abc"),
                        ("lower-scheme", "bearer garbage"), ("two-parts", "Bearer a b"), ("jwt-shaped", "Bearer a.b.c")]:
        steps.append(S(f"malformed.{sid}", "GET", "/api/me", headers={"authorization": header}))
    # --- each way a token can be wrong
    for name in ("expired", "not_yet_valid", "wrong_audience", "wrong_tenant", "wrong_issuer_v1", "forged", "missing_exp", "missing_iat"):
        steps.append(S(f"token.{name}", "GET", "/api/me", headers=bearer(name)))
    for name in ("no_scope", "no_role", "wrong_role", "user_with_agent_role", "agent_with_scope", "agent_wrong_role", "agent_no_role", "agent_named"):
        steps.append(S(f"token.{name}", "GET", "/api/me", headers=bearer(name)))
    steps += [S("token.bare-audience-ok", "GET", "/api/me", headers=bearer("bare_audience")), S("token.reader-me", "GET", "/api/me", headers=bearer("reader")),
              S("token.writer-me", "GET", "/api/me", headers=bearer("writer")), S("token.expired-on-public-health", "GET", "/api/health", headers=bearer("expired"))]
    # --- reader versus writer
    body = b.GOOD_BODY
    writes = [("claims-create", "POST", "/api/claims", body["POST /api/claims"]), ("engagement", "PUT", "/api/claims/engagement", body["PUT /api/claims/engagement"]),
              ("assess", "POST", "/api/claims/assess", body["POST /api/claims/assess"]),
              ("transition", "POST", "/api/claims/cell/1001/GA_JTC/2025/transition", body["POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition"]),
              ("run", "POST", "/api/v2/clients/1001/runs", body["POST /api/v2/clients/{client_id}/runs"]),
              ("base-year", "POST", "/api/v2/clients/1001/units/GA_ATL_HQ/base-year", body["POST /api/v2/clients/{client_id}/units/{unit_id}/base-year"]),
              ("draft-create", "POST", "/api/v2/program-drafts", body["POST /api/v2/program-drafts"]),
              ("finding-resolve", "POST", "/api/findings/policy:test_of_twos:ALL:2025/resolve", body["POST /api/findings/{finding_id}/resolve"]),
              ("rules-verify", "POST", "/api/rules/GA_JTC/verify", body["POST /api/rules/{code}/verify"]),
              ("batch-dry-run", "POST", "/api/v2/run-batches", body["POST /api/v2/run-batches"])]
    for who in ("reader", "writer"):
        for sid, method, path, payload in writes:
            steps.append(S(f"{who}.{sid}", method, path, json=payload, headers=bearer(who)))
    steps += [S("reader.read-portfolio", "GET", "/api/v2/portfolio", headers=bearer("reader")), S("reader.read-units", "GET", "/api/v2/clients/1001/units", query=[["year", 2025]], headers=bearer("reader"))]
    # --- the per-caller limit: 3 a minute, per kind, per caller; Retry-After from a frozen clock
    for i in range(1, 6):
        steps.append(S(f"ratelimit.writer-batch-{i}", "POST", "/api/v2/run-batches", json=body["POST /api/v2/run-batches"], headers=bearer("writer")))
    steps.append(S("ratelimit.reader-batch-1-own-bucket", "POST", "/api/v2/run-batches", json=body["POST /api/v2/run-batches"], headers=bearer("reader")))
    steps.append(S("ratelimit.writer-other-kind", "POST", "/api/v2/program-drafts/00000000-0000-0000-0000-000000000000/preview", json={"dataset": "synthetic_sample"}, headers=bearer("writer")))
    steps.append(S("ratelimit.writer-reads-unaffected", "GET", "/api/v2/portfolio", headers=bearer("writer")))
    # --- the client authorizer: another client's data is 403, an unknown batch is 404 and never 403
    r = bearer("restricted")
    steps += [S("client-authz.coverage", "GET", "/api/claims/coverage/1001", headers=r), S("client-authz.units", "GET", "/api/v2/clients/1001/units", headers=r),
              S("client-authz.query-account", "GET", "/api/eligibility/2025", query=[["state", "GA"], ["account_id", 1001]], headers=r),
              S("client-authz.body-client", "POST", "/api/claims/assess", json={"client_id": 1001, "assessed_by": "x"}, headers=r),
              S("client-authz.batch-names-client", "POST", "/api/v2/run-batches", json={"kind": "assess", "scope": {"kind": "list", "client_ids": [1001]}, "dry_run": True}, headers=r),
              S("client-authz.batch-scope-all", "POST", "/api/v2/run-batches", json={"kind": "assess", "scope": {"kind": "all"}, "dry_run": True}, headers=r),
              S("client-authz.unknown-batch-is-404", "GET", "/api/v2/run-batches/00000000-0000-0000-0000-000000000000", headers=r),
              S("client-authz.unknown-batch-items-is-404", "GET", "/api/v2/run-batches/00000000-0000-0000-0000-000000000000/items", headers=r),
              S("client-authz.artifact-self-authorizing", "GET", "/api/clients/1001/artifacts/00000000-0000-0000-0000-000000000000", headers=r),
              S("client-authz.portfolio-names-no-client", "GET", "/api/v2/portfolio", headers=r), S("client-authz.scope", "GET", "/api/scope", headers=r)]
    # --- agent tokens and the acting-user header
    ag = bearer("agent")
    steps += [S("agent.no-acting-header", "GET", "/api/me", headers=ag), S("agent.me-acting", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.acting-reader", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": acting(reader, assurance="delegated")}),
              S("agent.header-empty", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": ""}),
              S("agent.header-not-base64", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": "not base64!"}),
              S("agent.header-not-json", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": "YWJj"}),
              S("agent.header-wrong-tenant", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": encode({"oid": writer, "tid": "00000000-0000-0000-0000-0000000000ff"})}),
              S("agent.header-bad-oid", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": encode({"oid": "nope", "tid": tenant})}),
              S("agent.header-bad-channel", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": acting(writer, channel="fax")}),
              S("agent.header-bad-assurance", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": acting(writer, assurance="trust-me")}),
              S("agent.header-too-large", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": "A" * 3000}),
              S("agent.header-long-name", "GET", "/api/me", headers={**ag, "x-tcc-acting-user": acting(writer, name="n" * 300)}),
              S("user.acting-header-ignored", "GET", "/api/me", headers={**bearer("reader"), "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-assess", "POST", "/api/claims/assess", json=body["POST /api/claims/assess"], headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-run", "POST", "/api/v2/clients/1001/runs", json=body["POST /api/v2/clients/{client_id}/runs"], headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-batch", "POST", "/api/v2/run-batches", json=body["POST /api/v2/run-batches"], headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-draft-create", "POST", "/api/v2/program-drafts", json=body["POST /api/v2/program-drafts"], headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-draft-put", "PUT", "/api/v2/program-drafts/x/documents", json={"expected_version": 1, "pack": None}, headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-rules-verify", "POST", "/api/rules/GA_JTC/verify", json=body["POST /api/rules/{code}/verify"], headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-workspace-refresh", "POST", "/api/workspace/refresh", headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.forbidden-checked-before-header", "POST", "/api/claims/assess", json=body["POST /api/claims/assess"], headers=ag),
              S("agent.read-allowed", "GET", "/api/v2/portfolio", headers={**ag, "x-tcc-acting-user": acting(reader)}),
              S("agent.read-draft-list", "GET", "/api/v2/program-drafts", headers={**ag, "x-tcc-acting-user": acting(reader)}),
              S("agent.write-claims-as-writer", "POST", "/api/claims", json=body["POST /api/claims"], headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.write-transition-as-writer", "POST", "/api/claims/cell/1001/GA_JTC/2025/transition", json={**body["POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition"], "decided_by": "acting@example.test"}, headers={**ag, "x-tcc-acting-user": acting(writer)}),
              S("agent.write-transition-as-reader", "POST", "/api/claims/cell/1001/GA_JTC/2025/transition", json={**body["POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition"], "decided_by": "acting@example.test"}, headers={**ag, "x-tcc-acting-user": acting(reader)}),
              S("agent.capabilities-list", "GET", "/api/capabilities", headers={**ag, "x-tcc-acting-user": acting(reader)}),
              S("agent.capabilities-book-rank", "POST", "/api/capabilities/book_rank", json={"args": {}}, headers={**ag, "x-tcc-acting-user": acting(reader)}),
              S("agent.audit-channel", "GET", "/api/audit/channel", query=[["user_oid", reader]], headers={**ag, "x-tcc-acting-user": acting(reader)})]
    # --- CORS with and without proof
    steps += [S("cors.preflight-no-token", "OPTIONS", "/api/claims", headers={"origin": "https://example.test", "access-control-request-method": "POST", "access-control-request-headers": "authorization,content-type,x-tcc-acting-user"}),
              S("cors.simple-with-token", "GET", "/api/me", headers={**bearer("reader"), "origin": "https://example.test"}),
              S("cors.simple-401", "GET", "/api/me", headers={"origin": "https://example.test"}),
              S("cors.simple-403", "GET", "/api/me", headers={**bearer("no_role"), "origin": "https://example.test"}),
              S("cors.preflight-put", "OPTIONS", "/api/claims/engagement", headers={"origin": "https://example.test", "access-control-request-method": "PUT"}),
              S("cors.preflight-patch-disallowed", "OPTIONS", "/api/claims", headers={"origin": "https://example.test", "access-control-request-method": "PATCH"}),
              S("cors.preflight-delete-disallowed", "OPTIONS", "/api/claims", headers={"origin": "https://example.test", "access-control-request-method": "DELETE"})]
    return write("p1_auth", "P1", steps, auth={"rate_limit_per_minute": 3}, tokens=tokens, variables=VARS_P1)

