"""The orchestrator's pins and its documentation stay honest. [CH-08]"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = ROOT / "channel_orchestrator"


def pins(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s#;]+)", line.strip())
        if match:
            found[match.group(1).lower().replace("_", "-")] = match.group(2)
    return found


def test_every_shared_dependency_is_pinned_to_the_version_the_platform_runs():
    ours, theirs = pins(ORCHESTRATOR / "requirements.txt"), pins(ROOT / "backend" / "requirements.txt")
    shared = {"azure-identity", "httpx", "jsonschema", "azure-ai-projects"}
    assert shared <= set(ours)
    for name in shared:
        assert ours[name] == theirs[name], f"{name}: orchestrator {ours[name]} vs backend {theirs[name]}"


def test_the_agent_framework_pin_is_the_one_the_backends_foundry_package_resolves_to():
    import agent_framework

    assert pins(ORCHESTRATOR / "requirements.txt")["agent-framework-core"] == __import__("importlib.metadata", fromlist=["version"]).version("agent-framework-core")
    assert agent_framework is not None


def test_the_frameworks_openai_client_and_its_sdk_are_pinned_to_what_is_installed():
    from importlib.metadata import version

    ours = pins(ORCHESTRATOR / "requirements.txt")
    for name in ("agent-framework-openai", "openai"):
        assert ours[name] == version(name), f"{name}: orchestrator pins {ours[name]}, installed {version(name)}"


def test_the_orchestrator_does_not_install_the_backend_and_names_a_stable_hosting_package():
    text = "\n".join(l for l in (ORCHESTRATOR / "requirements.txt").read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
    assert "fastapi" not in text.lower() and "pyodbc" not in text.lower() and "-r " not in text
    assert "azure-ai-agentserver-responses==" in text
    assert not re.search(r"^agent-framework-foundry-hosting", text, re.MULTILINE), "a beta package needs --pre"


def test_every_variable_the_orchestrator_reads_is_in_the_environment_reference():
    source = (ORCHESTRATOR / "app" / "core" / "settings.py").read_text(encoding="utf-8") + (ORCHESTRATOR / "app" / "wiring.py").read_text(encoding="utf-8")
    read = set(re.findall(r'"((?:CHANNEL|TENANT|FOUNDRY)_[A-Z_]+|TENANT_ID)"', source))
    reference = (ROOT / "docs" / "architecture" / "ENV-VARS.md").read_text(encoding="utf-8")
    section = reference[reference.index("## 9b."): reference.index("## 10.")]
    missing = sorted(name for name in read if f"`{name}`" not in section)
    assert read and not missing, f"not in ENV-VARS.md section 9b: {missing}"


def test_the_decisions_the_docs_cite_exist():
    decisions = (ROOT / "docs" / "m365-channel" / "DECISIONS.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"\bD-(7[4-9]|8[0-9])\b", (ROOT / "docs" / "m365-channel" / "ORCHESTRATOR.md").read_text(encoding="utf-8")))
    for number in cited:
        assert re.search(rf"^## D-{number} ", decisions, re.MULTILINE), f"D-{number}"
