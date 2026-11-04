"""The orchestrator's boundaries are rules that fail the build, not conventions. [CH-08, ADR-003]

The orchestrator is the part of the system a language model can influence, so what it may import,
what it may send and what it may log are pinned here. Read these before adding a module.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[3] / "channel_orchestrator" / "app"
SOURCES = sorted(p for p in APP.rglob("*.py") if "vendor" not in p.parts)
STDLIB = __import__("sys").stdlib_module_names

#: Third-party packages the orchestrator may import, and the modules allowed each. The agent framework is the
#: MAF layer's alone: the `maf_*` modules (the agent, the generated tools, the middleware).
THIRD_PARTY = {
    "httpx": None, "jsonschema": None, "agent_framework": {p.name for p in SOURCES if p.name.startswith("maf_")},
    "agent_framework_openai": {"maf_foundry_client.py"},
    "azure": {"gateway_client.py", "main.py", "maf_foundry_client.py", "modelprobe.py"}, "opentelemetry": {"telemetry.py"},
}
#: The repo layers it may import (all vendored, all standard-library-only or model-access adapters).
LOCAL_OK = ("app", "application", "domain", "infrastructure.ai")
LOCAL_FORBIDDEN = ("api", "agents", "tools", "data", "config", "channel", "infrastructure.persistence", "application.wiring",
                   "application.queries", "application.commands", "application.mediator")
SECRETS = re.compile(r"token|authorization|bearer|password|secret|cookie|header", re.IGNORECASE)
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_there_are_modules_to_check():
    assert len(SOURCES) >= 14


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(APP)))
def test_imports_stay_inside_the_allowed_layers_and_packages(path):
    for module in imports(path):
        top = module.split(".")[0]
        if top in STDLIB or top == "__future__":
            continue
        if top in THIRD_PARTY:
            allowed = THIRD_PARTY[top]
            assert allowed is None or path.name in allowed, f"{path.name} may not import {module}"
            continue
        assert not module.startswith(LOCAL_FORBIDDEN), f"{path.name} imports {module}, a layer the orchestrator does not copy"
        assert module.startswith(LOCAL_OK), f"{path.name} imports {module}, which is neither the standard library nor allowed"


def test_only_main_imports_the_hosting_package():
    hosts = [p.name for p in SOURCES if any(m.startswith("azure.ai.agentserver") for m in imports(p))]
    assert hosts == ["main.py"]


def test_only_the_maf_layer_imports_the_agent_framework():
    users = [p.name for p in SOURCES if any(m.split(".")[0] in ("agent_framework", "agent_framework_openai") for m in imports(p))]
    assert "maf_agent.py" in users and all(name.startswith("maf_") for name in users), users


def constructors(name: str) -> list[str]:
    """The modules that CALL `name(...)` (a class built), not merely mention it."""
    return sorted({p.name for p in SOURCES for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
                   if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == name})


def test_the_model_path_is_chosen_in_one_place_and_each_client_is_built_in_one_module():
    """RM-09: `select_model_access` picks from AI_PROVIDER_CHAIN; the framework's OpenAI client is built by the
    foundry client module alone, `PortChatClient` by the agent module alone, and no key reaches either."""
    assert constructors("OpenAIChatCompletionClient") == ["maf_foundry_client.py"]
    assert constructors("FoundryModelAccess") == ["model_access.py"]
    assert constructors("PortChatClient") == ["maf_agent.py"]
    assert constructors("select_model_access") == ["wiring.py"]
    assert constructors("OpenAIChatClient") == [] and constructors("FoundryChatClient") == [], "FoundryChatClient targets a host the runtime cannot resolve (D-101)"
    for path in SOURCES:
        assert not re.search(r"\bapi_key\s*=|AZURE_OPENAI_API_KEY|OPENAI_API_KEY", path.read_text(encoding="utf-8")), f"{path.name} handles a model key"


def test_the_selection_and_the_shared_adapters_import_no_sdk():
    for name in ("model_access.py", "models.py", "maf_chat.py"):
        found = {m.split(".")[0] for m in imports(APP / "core" / name)}
        assert not found & {"azure", "openai", "agent_framework_openai", "agent_framework_foundry"}, f"{name} imports an SDK: {found}"
    assert "agent_framework" not in {m.split(".")[0] for m in imports(APP / "core" / "model_access.py")}


def test_the_commit_path_is_one_module_called_from_one_place():
    strings = {p.name for p in SOURCES for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith("_commit")}
    assert strings <= {"writes.py"}, f"a commit tool name is built outside writes.py: {strings}"
    callers = [p.name for p in SOURCES for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
               if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "commit_pending"]
    assert callers == ["turn.py"]
    constants = [p.name for p in SOURCES if "WRITE_COMMIT" in p.read_text(encoding="utf-8")]
    assert set(constants) <= {"toolset.py"}, "toolset.py excludes commits from the model's tools; nothing else needs the constant"


def test_nothing_logs_a_token_a_header_or_a_secret():
    bad = []
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            call = node if isinstance(node, ast.Call) else None
            if call and isinstance(call.func, ast.Attribute) and call.func.attr in LOG_METHODS and getattr(call.func.value, "id", "") in ("log", "logging"):
                if SECRETS.search(ast.unparse(call)):
                    bad.append(f"{path.name}:{call.lineno}")
    assert bad == []


def test_nothing_prints_and_nothing_catches_without_saying_why():
    for path in SOURCES:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*print\(", source, re.MULTILINE), path.name
        for number, line in enumerate(source.splitlines(), 1):
            if re.match(r"\s*except Exception", line):
                assert "noqa: BLE001" in line, f"{path.name}:{number} catches everything without a stated reason"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(APP)))
def test_modules_stay_small_and_documented(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 250, "split the module"
    assert ast.get_docstring(tree), "a module says what it is for"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.end_lineno - node.lineno + 1 <= 40, f"{node.name} is longer than 40 lines"
            assert len(node.args.args) + len(node.args.kwonlyargs) <= 7 or node.name == "__init__", f"{node.name} takes too many arguments"
