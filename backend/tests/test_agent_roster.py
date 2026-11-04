"""The agent list is read, validated and published as declared. [RM-11]

`agents/agents.json` is the one place a specialist prompt agent is declared. These tests
hold the reader to it: a malformed list is refused on import (not at the first publish), the
specs the publisher receives are exactly what the list says, and publishing behaves as it did
before the list existed (one version per agent, an identical definition reused, a changed
prompt published, no tool ever attached).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agents import roster
from agents.factory import all_specs, list_agent_modules
from agents.roster import RosterError, load_roster
from application.ai.settings import AiSettings
from domain.ai import ModelRole
from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog
from infrastructure.ai.prompts_fs import FilePromptStore

ENDPOINT = "https://acct.services.ai.azure.com/api/projects/proj"
DOCUMENT = json.loads(roster.ROSTER_FILE.read_text(encoding="utf-8"))


def write(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def variant(**changes):
    """A copy of the real list with `changes` applied to the top level."""
    return {**json.loads(json.dumps(DOCUMENT)), **changes}


# ----------------------------------------------------------- what the list says is what is built


def test_the_real_list_loads_and_declares_twelve_agents_without_tools():
    declared = load_roster()
    assert len(declared.agents) == 12
    assert all(d.tools == () for d in declared.agents)


def test_the_specs_the_publisher_receives_are_the_declarations():
    store = FilePromptStore()
    specs = {spec.name: spec for spec in all_specs()}
    for declaration in load_roster().agents:
        spec = specs[declaration.name]
        assert spec.role is declaration.role and spec.temperature == declaration.temperature
        assert spec.instructions == store.get(declaration.prompt).text


def test_the_modules_come_in_the_order_the_list_gives_them():
    assert [m.__name__.rsplit(".", 1)[-1] for m in list_agent_modules()] == [d.module for d in load_roster().agents]


def test_a_model_is_a_role_never_a_deployment_name():
    roles = {d.role for d in load_roster().agents}
    assert roles == {ModelRole.ROUTER, ModelRole.NARRATOR, ModelRole.ANALYSIS}
    assert not {"model", "deployment"} & {key for entry in DOCUMENT["agents"] for key in entry}


# ----------------------------------------------------------- a malformed list is refused


def broken(entry_changes: dict) -> dict:
    document = variant()
    document["agents"][0] = {**document["agents"][0], **entry_changes}
    return document


@pytest.mark.parametrize("document, expected", [
    (variant(format=2), "format 1"),
    (variant(agents="nope"), "format 1"),
    (broken({"role": "oracle"}), "role must be one of"),
    (broken({"temperature": 3}), "temperature"),
    (broken({"temperature": True}), "temperature"),
    (broken({"temperature": "0.2"}), "temperature"),
    (broken({"tools": ["calculate_credit"]}), "hold no tools"),
    (broken({"model": "a-deployment"}), "exactly the fields"),
    (broken({"name": ""}), "non-empty"),
    (broken({"prompt": "no_such_prompt"}), "no file"),
    (broken({"name": "ReportingAgent"}), "share a name"),
    (broken({"module": "reporting"}), "share a module"),
    (broken({"prompt": "reporting"}), "share a prompt"),
], ids=lambda value: value if isinstance(value, str) else "case")
def test_a_malformed_list_is_refused(tmp_path, document, expected):
    with pytest.raises(RosterError, match=expected):
        load_roster.__wrapped__(write(tmp_path, document))


def test_a_prompt_file_that_is_neither_an_agents_nor_excluded_is_refused(tmp_path):
    document = variant()
    removed = document["agents"].pop()
    with pytest.raises(RosterError, match=removed["prompt"]):
        load_roster.__wrapped__(write(tmp_path, document))


def test_excluding_a_prompt_needs_a_reason_and_a_real_unused_file(tmp_path):
    document = variant()
    removed = document["agents"].pop()["prompt"]
    assert load_roster.__wrapped__(write(tmp_path, {**document, "excluded_prompts": {removed: "kept as a reference"}}))
    for excluded in ({removed: ""}, {"no_such_prompt": "why"}, {"reporting": "still used"}):
        with pytest.raises(RosterError, match="excluded_prompts"):
            load_roster.__wrapped__(write(tmp_path, {**document, "excluded_prompts": excluded}))


# ----------------------------------------------------------- publishing is unchanged


class Versions:
    """The slice of `project.agents` the publisher uses, over an in-memory store."""

    def __init__(self) -> None:
        self.created: list[tuple[str, object]] = []
        self.store: dict[str, list] = {}

    def list_versions(self, name):
        return self.store.get(name, [])

    def get_version(self, name, version):
        return next(v for v in self.store[name] if str(v.version) == str(version))

    def create_version(self, name, definition):
        number = len(self.store.get(name, [])) + 1
        info = type("V", (), {"version": str(number), "id": f"{name}:{number}", "definition": definition})()
        self.store.setdefault(name, []).append(info)
        self.created.append((name, definition))
        return info


def catalog_over(versions: Versions, specs=None) -> FoundryAgentCatalog:
    models = {"router": "model-router", "narrator": "model-narrator", "analysis": "model-analysis"}
    client = type("C", (), {"agents": versions})()
    return FoundryAgentCatalog(
        AiSettings(foundry_endpoint=ENDPOINT, models=models), specs if specs is not None else all_specs(),
        client_factory=lambda: client, sleep=lambda s: None,
    )


def test_every_declared_agent_is_published_once_with_its_declared_instructions_and_no_tools():
    versions = Versions()
    catalog_over(versions).publish_all()
    declared = {d.name: d for d in load_roster().agents}
    assert sorted(name for name, _ in versions.created) == sorted(declared)
    store = FilePromptStore()
    for name, definition in versions.created:
        assert definition.instructions == store.get(declared[name].prompt).text
        assert definition.model == f"model-{declared[name].role.value}"
        assert not getattr(definition, "tools", None)


def test_publishing_again_reuses_the_identical_definitions():
    versions = Versions()
    catalog = catalog_over(versions)
    catalog.publish_all()
    catalog.publish_all()
    assert len(versions.created) == 12
    assert {entry.version for entry in catalog.entries()} == {"1"}


def test_a_changed_prompt_publishes_a_new_version_of_that_agent_only():
    versions = Versions()
    catalog_over(versions).publish_all()
    changed = [s if s.name != "ReportingAgent" else type(s)(
        name=s.name, instructions=s.instructions + "\nOne more rule.\n", role=s.role, temperature=s.temperature, profile=s.profile,
    ) for s in all_specs()]
    again = catalog_over(versions, changed)
    again.publish_all()
    assert [name for name, _ in versions.created].count("ReportingAgent") == 2
    assert len(versions.created) == 13
    assert again.version_of("ReportingAgent") == "2" and again.version_of("HeadcountAgent") == "1"


def test_a_copy_of_the_prompt_directory_cannot_hide_an_unlisted_prompt(tmp_path, monkeypatch):
    prompts = tmp_path / "prompts"
    shutil.copytree(roster.PROMPT_DIR, prompts)
    (prompts / "stray.md").write_text("---\nversion: 1\nowner: x\n---\nStray.\n", encoding="utf-8")
    monkeypatch.setattr(roster, "PROMPT_DIR", prompts)
    with pytest.raises(RosterError, match="stray"):
        load_roster.__wrapped__(roster.ROSTER_FILE)
