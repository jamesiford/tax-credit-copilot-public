"""Skill checks: the platform's ASKILL package rules and companion-file rules. [CH-10]

Implements, from the Cowork plugin documentation: ASKILL-P001..P008 (folder exists,
`SKILL.md`, frontmatter, `name` and `description`, name equals folder, kebab-case, no
duplicates), the companion-file limits (20 files, 5 MB each, 10 MB total) and path
rules, and one rule of ours: the body of a `SKILL.md` stays under about 5,000 tokens,
because a longer skill is one the model reads less carefully.
"""
from __future__ import annotations

import re
from typing import Any

from cowork_plugin import frontmatter
from cowork_plugin.findings import Finding

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9._ !-]+$")
RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))})
MAX_COMPANIONS, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_BODY_TOKENS = 20, 5 * 1024 * 1024, 10 * 1024 * 1024, 5000


def _folder(entry: Any) -> str:
    return str(entry.get("folder", "")).removeprefix("./").rstrip("/") if isinstance(entry, dict) else ""


def _path_problem(relative: str) -> str | None:
    parts = relative.split("/")
    if "\\" in relative or "\x00" in relative:
        return "backslash or null byte in the path"
    if relative.startswith("/") or ".." in parts:
        return "absolute path or path traversal"
    if any(part.startswith(".") for part in parts):
        return "hidden file"
    if any(part.split(".")[0].upper() in RESERVED for part in parts):
        return "Windows reserved name"
    if any(not SAFE_NAME.match(part) for part in parts):
        return "characters outside alphanumeric, hyphen, underscore, dot, space and '!'"
    return None


def _companions(folder: str, files: dict[str, bytes]) -> list[Finding]:
    prefix = folder + "/"
    own = {name: data for name, data in files.items() if name.startswith(prefix) and name != prefix + "SKILL.md"}
    found = [Finding("TCC-S002", folder, f"{len(own)} companion files; the limit is {MAX_COMPANIONS}")] if len(own) > MAX_COMPANIONS else []
    for name, data in own.items():
        problem = _path_problem(name[len(prefix):])
        if problem:
            found.append(Finding("TCC-S003", name, problem))
        if len(data) > MAX_FILE_BYTES:
            found.append(Finding("TCC-S002", name, "over 5 MB"))
    if sum(len(d) for d in own.values()) > MAX_TOTAL_BYTES:
        found.append(Finding("TCC-S002", folder, "companion files total over 10 MB"))
    return found


def _head(folder: str, files: dict[str, bytes]) -> tuple[dict[str, Any] | None, str, list[Finding]]:
    """The frontmatter and body of the folder's `SKILL.md`, or why not."""
    path = f"{folder}/SKILL.md"
    if not any(name.startswith(folder + "/") for name in files):
        return None, "", [Finding("ASKILL-P001", folder, "the folder is not in the package")]
    if path not in files:
        return None, "", [Finding("ASKILL-P002", folder, "the folder has no SKILL.md")]
    try:
        head, body = frontmatter.split(files[path].decode("utf-8"))
        return frontmatter.parse(head), body, []
    except (frontmatter.FrontmatterError, UnicodeDecodeError) as exc:
        return None, "", [Finding("ASKILL-P003", path, f"invalid frontmatter: {exc}")]


def _identity(folder: str, meta: dict[str, Any]) -> list[Finding]:
    path, found = f"{folder}/SKILL.md", []
    name, description = meta.get("name"), meta.get("description")
    if not isinstance(name, str) or not name:
        found.append(Finding("ASKILL-P004", path, "frontmatter needs a name"))
    else:
        if name != folder.rsplit("/", 1)[-1]:
            found.append(Finding("ASKILL-P006", path, f"name {name!r} does not match the folder"))
        if not KEBAB.match(name) or len(name) > 64:
            found.append(Finding("ASKILL-P007", path, "name must be kebab-case, 1-64 characters"))
    if not isinstance(description, str) or not description.strip():
        found.append(Finding("ASKILL-P005", path, "frontmatter needs a description"))
    elif len(description) > 1024:
        found.append(Finding("ASKILL-P005", path, f"description is {len(description)} characters; the limit is 1024"))
    return found


def validate_skills(manifest: dict[str, Any], files: dict[str, bytes]) -> list[Finding]:
    """Every skill problem: registered folders, their `SKILL.md`, their companions, and strays."""
    folders = [_folder(entry) for entry in manifest.get("agentSkills") or []]
    found = [Finding("ASKILL-P008", f, "listed more than once") for f in sorted({f for f in folders if folders.count(f) > 1})]
    for folder in dict.fromkeys(f for f in folders if f):
        meta, body, problems = _head(folder, files)
        found += problems
        if meta is not None:
            found += _identity(folder, meta)
            found += _companions(folder, files)
            if len(body) / 4 > MAX_BODY_TOKENS:
                found.append(Finding("TCC-S001", f"{folder}/SKILL.md", f"about {len(body) // 4} tokens; keep it under {MAX_BODY_TOKENS}"))
    registered = {f.split("/")[-1] for f in folders}
    strays = {n.split("/")[1] for n in files if n.startswith("skills/") and n.count("/") >= 2} - registered
    return found + [Finding("TCC-S004", f"skills/{s}", "has files but is not registered in agentSkills") for s in sorted(strays)]
