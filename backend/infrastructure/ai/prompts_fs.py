"""PromptStore over `backend/agents/prompts/*.md`. [AI-06]

A prompt is a file with front matter, because a prompt change is a behaviour
change: it needs an owner, a version and a changelog, and it must show up in
review as a diff of one file rather than inside a Python string.

    ---
    version: 3
    owner: product
    changelog:
      - "3: say 'recorded' not 'filed' (unverified claims)"
    ---
    <the instructions, byte for byte>

Everything after the closing `---` line is the prompt. It is returned verbatim —
including its trailing newline — because Foundry reuses a published agent version
only when the definition is IDENTICAL, so a stray whitespace edit would publish a
new version of every agent on the next startup.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from domain.ai import Prompt

PROMPT_DIR = Path(__file__).resolve().parents[2] / "agents" / "prompts"
_FRONT = re.compile(r"\A---\n(?P<head>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)


class PromptError(ValueError):
    """A prompt file is missing or malformed."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_prompt(name: str, raw: str) -> Prompt:
    """Parse one file's text. Line endings are normalised so the hash is platform-stable."""
    match = _FRONT.match(raw.replace("\r\n", "\n"))
    if not match:
        raise PromptError(f"{name}: a prompt file must start with a --- front matter block")
    fields = dict(
        line.split(":", 1) for line in match["head"].splitlines()
        if ":" in line and not line.startswith((" ", "-"))
    )
    try:
        version = int(fields["version"].strip())
        owner = fields["owner"].strip()
    except (KeyError, ValueError) as exc:
        raise PromptError(f"{name}: front matter needs an integer `version` and an `owner`") from exc
    text = match["body"]
    if not text.strip():
        raise PromptError(f"{name}: the prompt body is empty")
    return Prompt(name=name, version=version, owner=owner, text=text, sha256=sha256_text(text))


class FilePromptStore:
    """Reads prompts from a directory, once each."""

    def __init__(self, directory: Path = PROMPT_DIR) -> None:
        self._directory = directory
        self._cache: dict[str, Prompt] = {}

    def get(self, name: str) -> Prompt:
        if name not in self._cache:
            path = self._directory / f"{name}.md"
            if not path.is_file():
                raise PromptError(f"no prompt file for {name!r} at {path}")
            self._cache[name] = parse_prompt(name, path.read_text(encoding="utf-8"))
        return self._cache[name]

    def names(self) -> Sequence[str]:
        return sorted(p.stem for p in self._directory.glob("*.md"))
