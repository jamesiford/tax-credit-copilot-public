"""The prompt manifest: a prompt's text cannot change without its version changing. [AI-06]

`agents/prompts/manifest.json` records, for every prompt, the SHA-256 of the text at
each version it has had. The rule it enforces:

- the CURRENT text must hash to what is recorded for its CURRENT version, so editing
  the words without bumping `version` fails;
- bumping `version` is not enough on its own — the new hash has to be recorded
  (`refresh`), so the bump is a deliberate, reviewable line in the manifest;
- a recorded version's hash is never overwritten by `refresh`, so "I'll just
  refresh it" cannot paper over an un-bumped edit;
- every version needs a changelog line starting `N:` in the file's front matter.

Why: a prompt change is a behaviour change, and Foundry publishes a new agent
version whenever the text differs. This makes that visible in review as one line in
one file, and makes the audit trail's `agent_version` answer "which words were in
force".
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from infrastructure.ai.prompts_fs import PROMPT_DIR, FilePromptStore

MANIFEST_PATH = PROMPT_DIR / "manifest.json"
FORMAT = 1
_CHANGELOG_VERSION = re.compile(r'^\s+-\s+"?(\d+):', re.MULTILINE)


class ManifestError(ValueError):
    """`refresh` refused: it would hide an edit that was not versioned."""


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"format": FORMAT, "prompts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(manifest: Mapping[str, Any], path: Path = MANIFEST_PATH) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _changelog_versions(directory: Path, name: str) -> set[int]:
    head = (directory / f"{name}.md").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n---\n", 1)[0]
    return {int(v) for v in _CHANGELOG_VERSION.findall(head)}


def _problems_for(name: str, store: FilePromptStore, recorded: Mapping[str, str], directory: Path) -> list[str]:
    prompt = store.get(name)
    version = str(prompt.version)
    if version not in recorded:
        return [f"{name}: version {version} is not in the manifest — run scripts/prompt-manifest.py --refresh"]
    problems = []
    if recorded[version] != prompt.sha256:
        problems.append(f"{name}: the text changed but `version: {version}` did not — bump the version, add a changelog line, then refresh")
    if prompt.version < max(int(v) for v in recorded):
        problems.append(f"{name}: version {version} is older than a recorded version")
    if prompt.version not in _changelog_versions(directory, name):
        problems.append(f"{name}: the changelog has no line for version {version}")
    return problems


def check(store: FilePromptStore, manifest: Mapping[str, Any], directory: Path = PROMPT_DIR) -> list[str]:
    """Every way the prompts and the manifest disagree; empty when they agree."""
    entries = manifest.get("prompts", {})
    names = set(store.names())
    problems = [f"{n}: has no entry in the manifest — run scripts/prompt-manifest.py --refresh" for n in sorted(names - set(entries))]
    problems += [f"{n}: is in the manifest but has no prompt file" for n in sorted(set(entries) - names)]
    for name in sorted(names & set(entries)):
        problems += _problems_for(name, store, entries[name].get("versions", {}), directory)
    return problems


def refresh(store: FilePromptStore, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Record each prompt's current version. Never rewrites a version already recorded."""
    prompts = {name: {"versions": dict(entry.get("versions", {}))} for name, entry in manifest.get("prompts", {}).items()}
    for name in store.names():
        prompt = store.get(name)
        versions = prompts.setdefault(name, {"versions": {}})["versions"]
        known = versions.get(str(prompt.version))
        if known is not None and known != prompt.sha256:
            raise ManifestError(f"{name}: version {prompt.version} is recorded with different text — bump the version")
        versions[str(prompt.version)] = prompt.sha256
    return {"format": FORMAT, "prompts": prompts}
