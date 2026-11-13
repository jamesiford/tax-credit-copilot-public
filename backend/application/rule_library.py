"""Where the rule library reads its packs from: the API asks here rather than naming a folder. [ADR-013]"""
from __future__ import annotations

from pathlib import Path

from config import get_settings


def rules_dir() -> Path:
    """The folder rule packs are read from (`RULES_DIR`, default the packaged `backend/rules`)."""
    return get_settings().programs.rules_dir
