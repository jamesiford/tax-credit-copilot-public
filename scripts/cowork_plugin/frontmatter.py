"""A small reader for the `SKILL.md` frontmatter, no YAML library needed. [CH-10]

Skills use a deliberately narrow slice of YAML: top-level `key: value` pairs, quoted or
plain scalars, `|` / `>` block scalars (how a long `description` is written), and one
level of nested mapping (`metadata:`). The validator rejects anything outside that
slice as ASKILL-P003 rather than guessing, so a skill that this reader accepts is one
every YAML parser reads the same way.
"""
from __future__ import annotations

import re
from typing import Any

_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s+(.*))?$")


class FrontmatterError(ValueError):
    """The frontmatter is missing, unterminated, or outside the supported slice."""


def split(text: str) -> tuple[str, str]:
    """`(frontmatter, body)` of a skill file; raises when the `---` fences are not there."""
    lines = text.lstrip("\ufeff").split("\n")
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("the file does not start with a '---' line")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:])
    raise FrontmatterError("the frontmatter is not closed by a '---' line")


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw[:1] in "\"'[{&*!%@`":
        raise FrontmatterError(f"unsupported YAML value: {raw[:20]!r}")
    return raw


def _indented(lines: list[str], start: int) -> tuple[list[str], int]:
    block = []
    index = start
    while index < len(lines) and (not lines[index].strip() or lines[index][:1] in " \t"):
        block.append(lines[index])
        index += 1
    return block, index


def _mapping(block: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in block:
        if not line.strip():
            continue
        match = _KEY.match(line.strip())
        if not match:
            raise FrontmatterError(f"unsupported nested line: {line.strip()[:40]!r}")
        result[match.group(1)] = _scalar(match.group(2) or "")
    return result


def parse(frontmatter: str) -> dict[str, Any]:
    """The frontmatter as a dict of strings (or of one-level dicts of strings)."""
    lines, result, index = frontmatter.split("\n"), {}, 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _KEY.match(line)
        if not match:
            raise FrontmatterError(f"cannot read the line {line[:40]!r}")
        key, value = match.group(1), (match.group(2) or "").strip()
        block, index = _indented(lines, index)
        if value in ("|", ">", "|-", ">-"):
            joiner = "\n" if value.startswith("|") else " "
            result[key] = joiner.join(part.strip() for part in block if part.strip())
        elif value:
            result[key] = " ".join([_scalar(value), *(p.strip() for p in block if p.strip())])
        else:
            result[key] = _mapping(block)
    return result
