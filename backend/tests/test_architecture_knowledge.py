"""Nothing in the knowledge tier can write a fact. [RM-15, ADR-010]

Reference text is context, never a figure. The numeric guard trusts its facts (it reads numerals out of prose placed
among them), so the guarantee cannot be a property of the guard: it has to be that nothing the knowledge tier does can
reach the fact index, the fact ledger, a tool result or the reader's allowed numerals. These rules read the source to
keep that true, with an allow-list for what the tier may import and registries for who may touch it, so a change that
widens either is a deliberate edit with a reason in the same commit.

They also keep the tier honest about what exists: off by default, no SDK for the unbuilt Foundry IQ adapter, and no
Azure resource that the design needs (RM-15 created none).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
APP = ROOT / "channel_orchestrator" / "app"
KNOWLEDGE = [BACKEND / "application" / "knowledge" / f"{name}.py" for name in ("__init__", "port", "settings", "fake")]
PROVIDER = APP / "core" / "maf_knowledge.py"
TIER = [*KNOWLEDGE, PROVIDER]

#: What the knowledge tier may import, and nothing else (standard library aside): its own modules, the fence for
#: untrusted text, and for the provider the framework's context-provider types.
ALLOWED = {"application.knowledge", "application.knowledge.port", "application.knowledge.fake", "application.knowledge.settings", "application.ai.safety.untrusted"}
ALLOWED_THIRD_PARTY = {PROVIDER: {"agent_framework"}}
#: Names that mean "a fact" or "the ledger"; the tier uses none of them as a name, attribute or keyword.
FACT_NAMES = {"FactLedger", "FactIndex", "ToolRun", "ToolResult", "Envelope", "facts", "model_facts", "user_only_facts", "record",
              "verify_figures", "AllowedContext", "numeric_guard", "composer", "toolset"}
#: Who may import the tier, and why. Nothing on the figure path (guard, composer, ledger, tools, audit) is in it.
IMPORTERS = {
    "planned.py": "carries the passages a turn retrieved (the type)",
    "planner.py": "builds the provider for the agent path, only when a source was given",
    "turn.py": "prints the reference block beside a surviving narration",
    "wiring.py": "reads the settings at start and builds the source the settings ask for",
    "maf_knowledge.py": "the provider itself",
}
SDKS = ("azure.search", "azure.ai.projects.models.KnowledgeBase", "agent_framework_azure_ai_search", "agent_framework.azure")
PACKAGES = ("azure-search-documents", "agent-framework-azure-ai-search", "agent-framework-aisearch")


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imports(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def tier_findings(path: Path) -> list[str]:
    """Why this module could reach a fact, or []. Imports are an allow-list; names are a deny-list."""
    tree, found = parse(path), []
    third = ALLOWED_THIRD_PARTY.get(path, set())
    for name in sorted(imports(tree)):
        top = name.split(".")[0]
        local = top in {"application", "app", "channel", "domain", "infrastructure", "api", "tools"}
        if local and not any(name == a or name.startswith(a + ".") or a.startswith(name + ".") or a == name for a in ALLOWED):
            found.append(f"imports {name}")
        elif not local and top not in third and top not in __import__("sys").stdlib_module_names and top != "__future__":
            found.append(f"imports {name}")
    for node in ast.walk(tree):
        used = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else node.arg if isinstance(node, ast.keyword) else None
        if used in FACT_NAMES:
            found.append(f"uses the name {used}")
    return found


# --------------------------------------------------------------------------- what the tier can reach


@pytest.mark.parametrize("path", TIER, ids=lambda p: p.name)
def test_the_tier_imports_nothing_that_carries_a_fact_and_uses_no_fact_or_ledger_name(path):
    assert tier_findings(path) == [], path.name


def test_the_provider_may_only_add_instructions_to_the_context():
    calls = {node.func.attr for node in ast.walk(parse(PROVIDER)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "context"}
    assert calls == {"extend_instructions"}, "no tool, message or middleware: a provider here adds background text only"


def source_files(base: Path) -> list[Path]:
    skipped = {"tests", "vendor", ".venv", "__pycache__", "node_modules"}
    return [p for p in base.rglob("*.py") if not skipped & set(p.relative_to(base).parts)]


def test_only_the_registered_orchestrator_modules_import_the_tier_and_nothing_on_the_figure_path_does():
    importers = {}
    for path in source_files(APP):
        names = imports(parse(path))
        if any(n.startswith(("application.knowledge", "app.core.maf_knowledge")) for n in names):
            importers[path.name] = path
    assert set(importers) == set(IMPORTERS), f"the tier is imported by {sorted(importers)}; the registry says {sorted(IMPORTERS)}"


def test_the_backend_never_imports_the_tier_except_the_tier_itself():
    offenders = []
    for path in source_files(BACKEND):
        if path in KNOWLEDGE:
            continue
        if any(n.startswith("application.knowledge") for n in imports(parse(path))):
            offenders.append(path.relative_to(BACKEND).as_posix())
    assert offenders == [], f"the guard, composer, ledger, capabilities and the rest of the backend do not know the tier exists: {offenders}"


def test_the_ledger_is_written_by_the_gateway_pipeline_alone_and_built_by_the_gateway_wiring_alone():
    writers, builders = set(), set()
    for path in source_files(BACKEND):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "record" \
                    and "ledger" in ast.unparse(node.func.value).lower():
                writers.add(path.relative_to(BACKEND).as_posix())
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "FactLedger":
                builders.add(path.relative_to(BACKEND).as_posix())
    assert writers == {"channel/pipeline.py"} and builders == {"channel/wiring.py"}, (writers, builders)


# --------------------------------------------------------------------------- off by default, and nothing built for it


def test_the_settings_default_to_off():
    from application.knowledge.settings import KnowledgeSettings

    assert KnowledgeSettings().enabled is False and KnowledgeSettings().provider == "none"


def test_the_provider_is_built_in_the_planner_alone():
    builders = {p.name for p in source_files(APP) if any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "KnowledgeContextProvider"
                                                         for n in ast.walk(parse(p)))}
    assert builders == {"planner.py"}


def test_no_sdk_for_the_unbuilt_adapter_is_imported_or_required_anywhere():
    for base in (BACKEND, APP):
        for path in source_files(base):
            found = [n for n in imports(parse(path)) if n.startswith(SDKS)]
            assert not found, f"{path.relative_to(ROOT)} imports {found}: the Foundry IQ adapter is designed, not built (ADR-010)"
    for requirements in (BACKEND / "requirements.txt", ROOT / "channel_orchestrator" / "requirements.txt"):
        live = [l.split("==")[0].strip().lower() for l in requirements.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        assert not set(live) & set(PACKAGES), requirements.name


def test_no_azure_resource_for_knowledge_is_declared_and_the_switch_is_not_set_by_any_deployment_file():
    infra = [p for p in (ROOT / "infra").rglob("*") if p.suffix in {".tf", ".json", ".tfvars", ".yaml", ".yml"} and ".terraform" not in p.parts]
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in infra)
    assert not re.search(r"azurerm_search_service|Microsoft\.Search/searchServices|searchServices", text), "RM-15 creates no Search resource"
    deploy = text + (ROOT / "channel_orchestrator" / "azure.yaml").read_text(encoding="utf-8")
    assert "KNOWLEDGE_ENABLED" not in deploy and "KNOWLEDGE_PROVIDER" not in deploy


# --------------------------------------------------------------------------- the rules catch what they are meant to catch


@pytest.mark.parametrize("source, expected", [
    ("from channel.ledger import FactLedger\n", "imports channel.ledger"),
    ("from application.numeric.guard import check\n", "imports application.numeric.guard"),
    ("from application.composer import compose\n", "imports application.composer"),
    ("import httpx\n", "imports httpx"),
    ("def f(ledger):\n    ledger.record('c', 't', {})\n", "uses the name record"),
    ("x = dict(facts={})\n", "uses the name facts"),
    ("from application.numeric.facts import FactIndex\n", "imports application.numeric.facts"),
])
def test_the_scanner_finds_each_way_the_tier_could_reach_a_fact(tmp_path, source, expected):
    path = tmp_path / "knowledge_extra.py"
    path.write_text(source, encoding="utf-8")
    assert any(expected in finding for finding in tier_findings(path)), tier_findings(path)


def test_the_scanner_accepts_what_the_tier_really_imports(tmp_path):
    path = tmp_path / "ok.py"
    path.write_text("from application.knowledge import Passage\nfrom application.ai.safety.untrusted import UntrustedText\nimport re\n", encoding="utf-8")
    assert tier_findings(path) == []
