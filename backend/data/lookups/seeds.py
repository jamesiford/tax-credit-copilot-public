"""Versioned seed files: `backend/rules/lookups/<name>.v<N>.json`. [07]

A seed is data with provenance, so it can be audited like a rule pack: who wrote it, when, on what basis, and
whether it is `inferred` (a convention, not something the data owner told us). The highest version wins; an
older file stays in git as history.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[2] / "rules" / "lookups"
_NAME = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<version>\d+)\.json$")
_PROVENANCE = ("authored_by", "authored_on", "basis", "inferred")


class SeedError(ValueError):
    """A seed file is malformed or lacks provenance."""


@dataclass(frozen=True)
class Seed:
    name: str
    version: int
    inferred: bool
    provenance: dict
    entries: dict[str, str]


@lru_cache(maxsize=None)
def load_seed(name: str, directory: str | None = None) -> Seed | None:
    """The newest seed for `name`, or None when there is none."""
    root = Path(directory) if directory else SEED_DIR
    found = []
    for path in root.glob(f"{name}.v*.json"):
        match = _NAME.match(path.name)
        if match and match["name"] == name:
            found.append((int(match["version"]), path))
    if not found:
        return None
    version, path = max(found)
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in _PROVENANCE if k not in data]
    if missing or data.get("lookup") != name or data.get("version") != version:
        raise SeedError(f"{path.name}: missing {missing or 'consistent lookup/version'}; a seed carries its provenance")
    return Seed(name, version, bool(data["inferred"]), {k: data[k] for k in _PROVENANCE}, dict(data.get("entries") or {}))
