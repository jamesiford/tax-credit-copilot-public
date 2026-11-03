"""What a reader sees when no model could narrate. [AI-04]

The engine answers without a model; only the prose needs one. So when narration is
unavailable — every provider failed, or one died half way through a sentence — the
reader gets the engine's own figures, labelled as such, instead of an error token.

Nothing here is computed. The brief a pipeline hands an agent is JSON the engine
already produced; this flattens it to lines of `name: value`, unchanged, so what
appears is exactly what the model would have been given to restate.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

UNAVAILABLE_SENTENCE = "The assistant is unavailable; here are the engine's figures."
INTERRUPTED_SENTENCE = "The assistant was interrupted; the engine's figures follow."
MAX_LINES = 30
_MARKER = "JSON:\n"


def _brief_payload(prompt: str) -> Any:
    """The JSON object after the `JSON:` marker a pipeline's brief carries, or None."""
    start = prompt.find(_MARKER)
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(prompt[start + len(_MARKER):].lstrip())
    except ValueError:
        return None
    return value


def _leaves(value: Any, path: str) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value, 1):
            yield from _leaves(child, f"{path}[{index}]")
    elif value is not None:
        yield path, value


def figures_text(prompt: str) -> str:
    """The brief's values as bullet lines; empty when the prompt carries no brief."""
    payload = _brief_payload(prompt)
    if payload is None:
        return ""
    leaves = list(_leaves(payload, ""))
    lines = [f"- {name}: {value}" for name, value in leaves[:MAX_LINES]]
    if len(leaves) > MAX_LINES:
        lines.append(f"- … and {len(leaves) - MAX_LINES} more on the page.")
    return "\n".join(lines)


def degraded_message(prompt: str, *, interrupted: bool, with_sentence: bool) -> str:
    """The text to append. The sentence is omitted when it was already said once."""
    figures = figures_text(prompt)
    sentence = INTERRUPTED_SENTENCE if interrupted else UNAVAILABLE_SENTENCE
    parts = ([sentence] if with_sentence else []) + ([figures] if figures else [])
    if not parts:
        return ""
    return ("\n\n" if interrupted else "") + "\n\n".join(parts)
