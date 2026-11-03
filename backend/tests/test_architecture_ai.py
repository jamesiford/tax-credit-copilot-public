"""Model access is an infrastructure concern behind application ports. [AI-02]

The rule these tests hold: an SDK (`agent_framework*`, `azure.ai.*`, `openai`) is
imported only under `infrastructure/ai/`, and nothing above it knows which
provider answered. Before AI-02 the portal's chat called a `FoundryAgent` in
about twenty-five places, so a second provider meant editing every pipeline.

Kept in its own file so the existing architecture rules stay exactly as they
were; the helpers are theirs.
"""
from __future__ import annotations

import ast

import pytest

from tests.test_architecture import (
    BACKEND, _forbidden_imports, _import_modules, _non_stdlib_imports, _python_files,
)

_SDKS = ("agent_framework", "azure.ai", "openai")
_FRAMEWORKS = ("fastapi", "starlette", "api", "agents", "httpx", *_SDKS)


def _all_backend_modules():
    skip = ("tests", "scripts", "infrastructure/ai", ".venv", "node_modules")
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if "__pycache__" in path.parts or any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        yield rel, path


def test_no_sdk_is_imported_outside_infrastructure_ai():
    violations = []
    for rel, path in _all_backend_modules():
        bad = _forbidden_imports(path.read_text(encoding="utf-8"), _SDKS)
        if bad:
            violations.append(f"{rel} -> {bad}")
    assert not violations, "SDK imports outside infrastructure/ai/:\n  " + "\n  ".join(violations)


@pytest.mark.parametrize("package", ["api", "application"])
def test_httpx_for_model_calls_stays_in_infrastructure(package):
    """`api/` and `application/` never call a model over HTTP; adapters do."""
    bad = [
        p.relative_to(BACKEND).as_posix() for p in _python_files(package)
        if _forbidden_imports(p.read_text(encoding="utf-8"), ("httpx",))
    ]
    assert not bad, f"httpx imported in {bad}; model calls belong in infrastructure/ai/"


def test_application_ai_imports_no_framework_and_no_adapter():
    violations = []
    for path in _python_files("application/ai"):
        source = path.read_text(encoding="utf-8")
        bad = _forbidden_imports(source, (*_FRAMEWORKS, "infrastructure"))
        if bad:
            violations.append(f"{path.relative_to(BACKEND).as_posix()} -> {bad}")
    assert not violations, "application/ai/ imports outward:\n  " + "\n  ".join(violations)


def test_the_ai_domain_types_are_standard_library_only():
    """Stdlib plus the domain's own sibling (`ai_errors`, split out for size and re-exported)."""
    for module in ("ai.py", "ai_errors.py"):
        imports = _non_stdlib_imports((BACKEND / "domain" / module).read_text(encoding="utf-8"))
        assert [i for i in imports if i != "domain.ai_errors"] == [], module


def test_ports_are_small():
    """Interface segregation: at most six methods per port."""
    tree = ast.parse((BACKEND / "application" / "ai" / "ports.py").read_text(encoding="utf-8"))
    oversized = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
            if len(methods) > 6:
                oversized[node.name] = len(methods)
    assert not oversized, f"ports over six methods: {oversized}"


def test_the_expected_ports_exist():
    tree = ast.parse((BACKEND / "application" / "ai" / "ports.py").read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    assert {
        "ChatModel", "AgentRuntime", "AgentCatalog", "PromptStore", "AiTelemetry", "TokenBudget",
        "ConversationStore", "OutputPolicy", "EgressPolicy",
    } <= names


def test_no_api_module_references_a_foundry_agent():
    bad = [
        p.relative_to(BACKEND).as_posix() for p in _python_files("api")
        if "FoundryAgent" in p.read_text(encoding="utf-8")
    ]
    assert not bad, f"{bad} mention FoundryAgent; the API sees `NarrateBriefQuery`, not an SDK object"


def test_streaming_queries_are_queries():
    from application.mediator import Query, StreamingQuery

    assert issubclass(StreamingQuery, Query)


def test_the_ai_rules_catch_a_crafted_violation():
    """A rule nobody has seen fail is a rule nobody knows works."""
    assert _forbidden_imports("from openai import OpenAI", _SDKS) == ["openai"]
    assert _forbidden_imports("import agent_framework_foundry", _SDKS) == ["agent_framework_foundry"]
    assert _forbidden_imports("from azure.ai.projects import AIProjectClient", _SDKS)
    assert _forbidden_imports("import httpx", _FRAMEWORKS) == ["httpx"]
    assert _forbidden_imports("from infrastructure.ai import prompts_fs", ("infrastructure",))
    assert "openai" in _import_modules("import openai")
