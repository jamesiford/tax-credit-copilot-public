"""Where the program registry and the rule packs are read from. [ADR-013]

Both default to the folder that ships with the backend. A test or a deployment can point at another folder, so a
program can be added without touching the source tree; the registry file defaults to `registry/programs.json` inside
whichever rules folder is in force.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_PACKAGED_RULES = Path(__file__).resolve().parent / "rules"


@dataclass(frozen=True)
class ProgramSettings:
    """The rules folder and the registry manifest, both absolute."""

    rules_dir: Path = _PACKAGED_RULES
    registry_file: Path = _PACKAGED_RULES / "registry" / "programs.json"


def parse_programs(environ: Mapping[str, str]) -> ProgramSettings:
    """`RULES_DIR` (default the packaged `backend/rules`) and `PROGRAM_REGISTRY_FILE` (default `<RULES_DIR>/registry/programs.json`)."""
    raw_dir = (environ.get("RULES_DIR") or "").strip()
    rules_dir = Path(raw_dir).expanduser().resolve() if raw_dir else _PACKAGED_RULES
    raw_file = (environ.get("PROGRAM_REGISTRY_FILE") or "").strip()
    registry = Path(raw_file).expanduser().resolve() if raw_file else rules_dir / "registry" / "programs.json"
    return ProgramSettings(rules_dir=rules_dir, registry_file=registry)
