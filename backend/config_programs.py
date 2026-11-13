"""Where the program registry and the rule packs are read from, and how program drafts are governed. [ADR-013, F05]

Both paths default to the folder that ships with the backend. A test or a deployment can point at another folder, so a
program can be added without touching the source tree; the registry file defaults to `registry/programs.json` inside
whichever rules folder is in force.

The draft settings are about who may approve and what a preview may read, never about statute: a draft has no runtime
authority whatever they say. [ADR-005]
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from config_values import optional_flag

_PACKAGED_RULES = Path(__file__).resolve().parent / "rules"


@dataclass(frozen=True)
class ProgramSettings:
    """The rules folder and the registry manifest (both absolute), and the program-draft governance switches."""

    rules_dir: Path = _PACKAGED_RULES
    registry_file: Path = _PACKAGED_RULES / "registry" / "programs.json"
    draft_require_second_reviewer: bool = False
    preview_allow_customer_data: bool = False
    export_allow_local_write: bool = False


def parse_programs(environ: Mapping[str, str]) -> ProgramSettings:
    """`RULES_DIR` (default the packaged `backend/rules`) and `PROGRAM_REGISTRY_FILE` (default `<RULES_DIR>/registry/programs.json`).

    `PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER` defaults to true outside `ENVIRONMENT=local`; `PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA`
    defaults to false; `PROGRAM_EXPORT_ALLOW_LOCAL_WRITE` defaults to false and is honoured only in `ENVIRONMENT=local`.
    """
    raw_dir = (environ.get("RULES_DIR") or "").strip()
    rules_dir = Path(raw_dir).expanduser().resolve() if raw_dir else _PACKAGED_RULES
    raw_file = (environ.get("PROGRAM_REGISTRY_FILE") or "").strip()
    registry = Path(raw_file).expanduser().resolve() if raw_file else rules_dir / "registry" / "programs.json"
    local = (environ.get("ENVIRONMENT") or "local").strip().lower() == "local"
    second = optional_flag(environ, "PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER")
    write = optional_flag(environ, "PROGRAM_EXPORT_ALLOW_LOCAL_WRITE")
    return ProgramSettings(
        rules_dir=rules_dir, registry_file=registry,
        draft_require_second_reviewer=(not local) if second is None else second,
        preview_allow_customer_data=bool(optional_flag(environ, "PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA")),
        export_allow_local_write=local and bool(write),
    )
