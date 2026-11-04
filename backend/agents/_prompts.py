"""Load an agent's instructions from its versioned prompt file. [AI-06]

The text lives in `agents/prompts/<module>.md`, not in Python, so changing what an
agent is told is a reviewable one-file diff with a version bump (a test refuses
the edit otherwise).
"""
from __future__ import annotations

from infrastructure.ai.prompts_fs import FilePromptStore

_STORE = FilePromptStore()


def load_instructions(module_stem: str) -> str:
    """The verbatim prompt body for `agents/prompts/<module_stem>.md`."""
    return _STORE.get(module_stem).text
