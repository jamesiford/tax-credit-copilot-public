"""The MCP facade stays hand-written until a re-check says otherwise: the decision is a test. [RM-14, D-136]

`channel/mcp.py` is hand-written because the `mcp` SDK's server cannot bind a session to the person who opened it (a
second person's calls join the first person's conversation, so `verify_figures` would check one person's draft against
another's facts) and answers an unauthenticated call with a JSON-RPC error and HTTP 200, not a 401. RM-14 measured that
on 2.3.0. Switching is a decision with consequences (a new dependency set in the API image, a session binding written
anyway), so it must be an edit to THIS file, with the evidence, and not a quiet import.

* no production module imports the SDK or its transport stack;
* the SDK is not a runtime requirement of the API, the gateway or the orchestrator, and is pinned for the tests;
* only the conformance test uses the SDK, and only its CLIENT.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
SDK = {"mcp", "mcp_types", "httpx2", "sse_starlette"}
PRODUCTION_ROOTS = (BACKEND, ROOT / "channel_orchestrator", ROOT / "scripts")
SKIP = {"tests", "__pycache__", ".venv", "venv", "node_modules", "vendored", "_vendored"}


def imported_roots(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return found


def production_modules() -> list[Path]:
    return [p for root in PRODUCTION_ROOTS for p in root.rglob("*.py") if SKIP.isdisjoint(p.relative_to(ROOT).parts)]


def test_production_code_is_found():
    names = {p.name for p in production_modules()}
    assert {"mcp.py", "routes.py", "pipeline.py"} <= names


def test_no_production_module_imports_the_mcp_sdk_or_its_transport_stack():
    offenders = {str(p.relative_to(ROOT)): sorted(imported_roots(p.read_text(encoding="utf-8")) & SDK)
                 for p in production_modules() if imported_roots(p.read_text(encoding="utf-8")) & SDK}
    assert not offenders, f"the facade is hand-written (D-136); switching to the SDK is a decision, not an import: {offenders}"


def test_the_sdk_is_a_test_requirement_only_and_is_pinned():
    runtime = [BACKEND / "requirements.txt", ROOT / "channel_orchestrator" / "requirements.txt"]
    for path in runtime:
        names = {line.split("==")[0].strip().lower().replace("_", "-") for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")}
        assert not {"mcp", "httpx2", "sse-starlette", "mcp-types"} & names, path.name
    tests = [line for line in (BACKEND / "requirements-test.txt").read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    assert tests == ["mcp==2.3.0"]


def test_only_the_conformance_test_uses_the_sdk_and_only_its_client():
    users = {p.name: imported_roots(p.read_text(encoding="utf-8")) & SDK for p in (BACKEND / "tests").rglob("test_*.py")
             if imported_roots(p.read_text(encoding="utf-8")) & SDK and p.name != Path(__file__).name}
    assert set(users) == {"test_gw_mcp_conformance.py"}, users
    source = (BACKEND / "tests" / "channel" / "test_gw_mcp_conformance.py").read_text(encoding="utf-8")
    assert "mcp.server" not in source and "streamable_http_app" not in source and "from mcp import Client" in source
