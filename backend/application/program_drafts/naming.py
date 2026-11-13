"""Where a draft's files would live, and its registry entry: one derivation for validation, preview and export. [F05, ADR-013]

A draft stores documents, not paths. These functions say what each would be called in the rules folder, so the validator's
file-name rule, the export bundle and the registry patch cannot disagree.
"""
from __future__ import annotations

from typing import Any

from domain.program_drafts import ProgramDraft


def pack_slug(code: str, state: str | None) -> str:
    """The program code without its leading state (`GA_JTC` in GA -> `jtc`), lower case, for the pack file name."""
    lowered, prefix = code.lower(), f"{(state or '').lower()}_"
    return lowered[len(prefix):] if state and lowered.startswith(prefix) and len(lowered) > len(prefix) else lowered


def pack_file_name(draft: ProgramDraft) -> str:
    """`<state>_<slug>.json`, the name the validator requires of a state pack."""
    return f"{(draft.state or '').lower()}_{pack_slug(draft.proposed_code, draft.state)}.json"


def year_file_name(year: str) -> str:
    return f"{year}.json"


def registry_entry(draft: ProgramDraft) -> dict[str, Any]:
    """The registry manifest entry a human adds: `described`, never `calculable`, which is derived from authored years."""
    return {
        "code": draft.proposed_code, "name": draft.name, "jurisdiction": {"level": draft.jurisdiction_level, "code": draft.state},
        "state": draft.state, "pack_file": pack_file_name(draft), "lifecycle": "described",
        "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"},
        "notes": "Added from a reviewed draft. Statute values are not verified until a person verifies each against the primary source.",
    }
