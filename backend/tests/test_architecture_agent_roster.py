"""The agent list is the only place an agent is declared. [RM-11]

Declaring an agent used to be twelve modules each carrying a name, a prompt call, a model
role and a temperature, plus a hand-kept import list. These rules read the source so that
cannot grow back: a second declaration of any of them fails the build, and so does a prompt
file nobody references.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agents.roster import ROSTER_FILE

BACKEND = Path(__file__).resolve().parents[1]
AGENTS = BACKEND / "agents"
INFRASTRUCTURE_FILES = {"__init__", "_prompts", "factory", "roster"}
DECLARED = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def agent_module_files() -> list[Path]:
    return sorted(p for p in AGENTS.glob("*.py") if p.stem not in INFRASTRUCTURE_FILES)


def runtime_sources() -> list[Path]:
    skipped = {"tests", ".venv", "venv", "node_modules", "__pycache__"}
    return [p for p in BACKEND.rglob("*.py") if not skipped & set(p.relative_to(BACKEND).parts)]


def called_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
    return names


def module_findings(path: Path) -> list[str]:
    """Why this agent module declares something the list owns, or []."""
    tree, found = parse(path), []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = {a.name for a in node.names} | {getattr(node, "module", None) or ""}
            if {"load_instructions", "ModelRole", "AgentSpec"} & imported or "_prompts" in imported:
                found.append("imports what only agents/roster.py may use (load_instructions, ModelRole, AgentSpec)")
    if {"AgentSpec", "load_instructions"} & called_names(tree):
        found.append("constructs a spec or loads a prompt itself")
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NAME" for t in node.targets):
            if not (isinstance(node.value, ast.Attribute) and ast.unparse(node.value) == "SPEC.name"):
                found.append("NAME is not SPEC.name")
    spec = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SPEC" for t in n.targets)]
    expected = f'build_spec({path.stem!r}, AGENT_PROFILE)'
    if len(spec) != 1 or ast.unparse(spec[0].value) != expected:
        found.append(f"SPEC must be exactly {expected}")
    return found


def test_every_agent_module_takes_its_declaration_from_the_list():
    assert agent_module_files(), "no agent modules found"
    for path in agent_module_files():
        assert module_findings(path) == [], path.name


def test_the_list_and_the_modules_name_each_other_exactly():
    assert sorted(p.stem for p in agent_module_files()) == sorted(entry["module"] for entry in DECLARED["agents"])


def test_only_the_roster_builds_an_agent_spec_or_loads_a_prompt_for_one():
    allowed = {AGENTS / "roster.py", BACKEND / "domain" / "ai.py"}
    offenders = []
    for path in runtime_sources():
        if path in allowed:
            continue
        tree = parse(path)
        if {"AgentSpec", "load_instructions"} & called_names(tree):
            offenders.append(path.relative_to(BACKEND).as_posix())
    assert offenders == [], f"an agent is declared outside agents/agents.json: {offenders}"


def test_the_publisher_is_fed_by_the_roster_and_nothing_else():
    wiring = (BACKEND / "application" / "ai_wiring.py").read_text(encoding="utf-8")
    assert "from agents.factory import all_specs" in wiring and "SpecRegistry(all_specs())" in wiring
    for stem in ("foundry_prompt_agents", "foundry_publish", "foundry_model_connection"):
        text = (BACKEND / "infrastructure" / "ai" / f"{stem}.py").read_text(encoding="utf-8")
        assert "agents.factory" not in text and "list_agent_modules" not in text, stem


def test_every_prompt_file_is_an_agents_or_excluded_with_a_reason():
    present = {p.stem for p in (AGENTS / "prompts").glob("*.md")}
    used = {entry["prompt"] for entry in DECLARED["agents"]}
    excluded = DECLARED["excluded_prompts"]
    assert used <= present, f"declared prompts with no file: {sorted(used - present)}"
    assert not present - used - set(excluded), f"prompts nobody references: {sorted(present - used - set(excluded))}"
    assert all(isinstance(reason, str) and reason.strip() for reason in excluded.values())
    assert not set(excluded) & used


# ------------------------------------------------ the rule catches what it is meant to catch


SPEC_LINE = "SPEC = build_spec('x', AGENT_PROFILE)\n"


@pytest.mark.parametrize("source, expected", [
    ("from domain.ai import AgentSpec\n" + SPEC_LINE, "imports what only"),
    ("from ._prompts import load_instructions\n" + SPEC_LINE, "imports what only"),
    ("from domain.ai import ModelRole\n" + SPEC_LINE, "imports what only"),
    ('NAME = "XAgent"\n' + SPEC_LINE, "NAME is not SPEC.name"),
    ("SPEC = AgentSpec(name='X', instructions='i')\n", "constructs a spec"),
    ("INSTRUCTIONS = load_instructions('x')\n" + SPEC_LINE, "constructs a spec or loads a prompt"),
    ("SPEC = build_spec('other', AGENT_PROFILE)\n", "SPEC must be exactly"),
    ("x = 1\n", "SPEC must be exactly"),
])
def test_the_module_rule_names_each_second_declaration(tmp_path, source, expected):
    path = tmp_path / "x.py"
    path.write_text(source, encoding="utf-8")
    assert any(expected in finding for finding in module_findings(path)), module_findings(path)


def test_the_module_rule_accepts_the_shape_every_module_has(tmp_path):
    path = tmp_path / "x.py"
    path.write_text("from .roster import build_spec\nAGENT_PROFILE = {}\n" + SPEC_LINE + "NAME = SPEC.name\nINSTRUCTIONS = SPEC.instructions\n", encoding="utf-8")
    assert module_findings(path) == []


def test_a_spec_built_outside_the_roster_would_be_found(tmp_path):
    path = tmp_path / "elsewhere.py"
    path.write_text("from domain.ai import AgentSpec\nS = AgentSpec(name='A', instructions='i')\n", encoding="utf-8")
    assert "AgentSpec" in called_names(parse(path))
