"""Reads the program registry: the one list of programs, as data. [ADR-013]

`rules/registry/programs.json` (or `PROGRAM_REGISTRY_FILE`) names every program, its pack file and the supported
models it uses. Nothing here reads statute: pack contents stay in `credit_math` and the year packs, and whether a
program is calculable is derived from the authored year packs, never typed into the manifest. [ADR-005]

`STATE_TO_PACK` and `PROGRAM_CODE_TO_PACK` in `tools/credit_math.py` are views over this registry, so there is one
answer to "which programs exist" and adding one is a manifest entry plus a pack, not an edit to a dictionary.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from config import get_settings
from domain.programs import (
    JURISDICTION_LEVELS,
    STORED_LIFECYCLES,
    SUPPORTED_CREDIT_MODELS,
    SUPPORTED_HEADCOUNT_MODELS,
    EngineProfile,
    ProgramEntry,
    RegistryError,
)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Registry:
    """The parsed manifest: entries in manifest order, and the folder their pack files live in."""

    entries: tuple[ProgramEntry, ...]
    rules_dir: Path
    source: Path

    def get(self, code: str) -> ProgramEntry | None:
        """The entry for a program code (case-insensitive), retired ones included, or None."""
        wanted = (code or "").upper()
        return next((e for e in self.entries if e.code == wanted), None)

    def active(self) -> tuple[ProgramEntry, ...]:
        """Entries the engine will resolve: everything not retired."""
        return tuple(e for e in self.entries if e.lifecycle != "retired")

    def code_to_pack(self) -> dict[str, str]:
        """Non-federal programs, code to pack file: the content of `PROGRAM_CODE_TO_PACK`."""
        return {e.code: e.pack_file for e in self.active() if e.level != "federal"}

    def state_to_pack(self) -> dict[str, str]:
        """State to pack file, the first listed program per state winning: the content of `STATE_TO_PACK`."""
        out: dict[str, str] = {}
        for entry in self.active():
            if entry.state and entry.state not in out:
                out[entry.state] = entry.pack_file
        return out

    def for_state(self, state: str) -> tuple[ProgramEntry, ...]:
        """Every non-retired program of a state, in manifest order.

        The first is the state's DEFAULT program: it is what `state_to_pack` (and so `STATE_TO_PACK`) shows, so
        reordering the manifest changes the default, and a state with one program is unaffected. [F04c.1]
        """
        wanted = (state or "").upper()
        return tuple(e for e in self.active() if e.state == wanted)

    def federal(self) -> tuple[ProgramEntry, ...]:
        """Federal-level programs, which have no state key and are found by jurisdiction level."""
        return tuple(e for e in self.active() if e.level == "federal")


def _fail(source: Path, where: str, message: str) -> RegistryError:
    return RegistryError(f"{source.name}: {where}: {message}")


def _parse_profile(raw: object, source: Path, where: str) -> EngineProfile:
    if raw is None:
        return EngineProfile()
    if not isinstance(raw, dict):
        raise _fail(source, where, "engine_profile must be an object")
    profile = EngineProfile(
        credit_model=str(raw.get("credit_model", EngineProfile.credit_model)),
        headcount_model=str(raw.get("headcount_model", EngineProfile.headcount_model)),
    )
    if profile.credit_model not in SUPPORTED_CREDIT_MODELS:
        raise _fail(source, where, f"credit_model {profile.credit_model!r} is not supported "
                    f"(supported: {', '.join(SUPPORTED_CREDIT_MODELS)}); a new model needs engine work")
    if profile.headcount_model not in SUPPORTED_HEADCOUNT_MODELS:
        raise _fail(source, where, f"headcount_model {profile.headcount_model!r} is not supported "
                    f"(supported: {', '.join(SUPPORTED_HEADCOUNT_MODELS)}); a new model needs engine work")
    return profile


def _parse_jurisdiction(raw: dict, source: Path, where: str) -> tuple[str, str, str | None]:
    """`(level, jurisdiction code, state)` from an entry, checking the level and the state rule for it."""
    jurisdiction = raw["jurisdiction"]
    level = jurisdiction.get("level") if isinstance(jurisdiction, dict) else None
    if level not in JURISDICTION_LEVELS:
        raise _fail(source, where, f"jurisdiction.level must be one of {', '.join(JURISDICTION_LEVELS)}")
    if not jurisdiction.get("code"):
        raise _fail(source, where, "jurisdiction.code is missing")
    state = raw.get("state")
    if level == "state" and not state:
        raise _fail(source, where, "a state-level program needs a state")
    if level == "federal" and state:
        raise _fail(source, where, "a federal program has no state key")
    return level, str(jurisdiction["code"]), (str(state).upper() if state else None)


def _parse_lifecycle(raw: dict, source: Path, where: str) -> str:
    lifecycle = str(raw.get("lifecycle", "described"))
    if lifecycle == "calculable":
        raise _fail(source, where, "lifecycle 'calculable' cannot be typed: it is derived from authored year packs")
    if lifecycle not in STORED_LIFECYCLES:
        raise _fail(source, where, f"lifecycle must be one of {', '.join(STORED_LIFECYCLES)}")
    return lifecycle


def _parse_entry(raw: object, index: int, source: Path, rules_dir: Path) -> ProgramEntry:
    where = f"programs[{index}]"
    if not isinstance(raw, dict):
        raise _fail(source, where, "an entry must be an object")
    for key in ("code", "name", "jurisdiction", "pack_file"):
        if not raw.get(key):
            raise _fail(source, where, f"missing {key}")
    code = str(raw["code"])
    where = f"program {code}"
    level, jurisdiction_code, state = _parse_jurisdiction(raw, source, where)
    lifecycle = _parse_lifecycle(raw, source, where)
    pack_file = str(raw["pack_file"])
    if lifecycle != "draft" and not (rules_dir / pack_file).is_file():
        raise _fail(source, where, f"pack_file {pack_file} not found in {rules_dir}")
    return ProgramEntry(
        code=code, name=str(raw["name"]), level=level, jurisdiction_code=jurisdiction_code,
        pack_file=pack_file, state=state, lifecycle=lifecycle,
        engine_profile=_parse_profile(raw.get("engine_profile"), source, where), notes=str(raw.get("notes", "")),
    )


def parse_registry(text: str, source: Path, rules_dir: Path) -> Registry:
    """Parse and check manifest text. Raises `RegistryError` naming the entry and the field."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise _fail(source, "file", f"not valid JSON ({exc})") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise _fail(source, "file", f"schema_version must be {SCHEMA_VERSION}")
    programs = data.get("programs")
    if not isinstance(programs, list):
        raise _fail(source, "file", "programs must be a list")
    entries = tuple(_parse_entry(raw, i, source, rules_dir) for i, raw in enumerate(programs))
    seen: set[str] = set()
    for entry in entries:
        if entry.code in seen:
            raise _fail(source, f"program {entry.code}", "code is listed twice")
        seen.add(entry.code)
    return Registry(entries=entries, rules_dir=rules_dir, source=source)


_cache: dict[tuple[Path, Path], tuple[int, Registry]] = {}
_lock = threading.Lock()


def load_registry() -> Registry:
    """The registry for the rules folder and manifest now in force, re-read when the manifest file changes."""
    settings = get_settings().programs
    key = (settings.registry_file, settings.rules_dir)
    try:
        stamp = settings.registry_file.stat().st_mtime_ns
    except FileNotFoundError as exc:
        raise RegistryError(f"program registry not found: {settings.registry_file}") from exc
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
        registry = parse_registry(settings.registry_file.read_text(encoding="utf-8"), settings.registry_file, settings.rules_dir)
        _cache[key] = (stamp, registry)
        return registry


def programs_for_state(state: str) -> tuple[ProgramEntry, ...]:
    """The state's programs, calculable and described alike, in stable registry order (first = default)."""
    return load_registry().for_state(state)


def program_for_code(code: str) -> ProgramEntry | None:
    """The active entry for a program code (case-insensitive); None when unknown or retired."""
    entry = load_registry().get(code)
    return entry if entry is not None and entry.lifecycle != "retired" else None


def rules_dir() -> Path:
    """The folder rule packs are read from (`RULES_DIR`)."""
    return get_settings().programs.rules_dir


class RegistryView(Mapping[str, str]):
    """A read-only mapping computed from the registry each time it is read, so a changed `RULES_DIR` is honoured.

    It stands in for the two dictionaries `credit_math` used to hardcode and compares equal to a plain dict with the
    same contents, so every existing import keeps working.
    """

    def __init__(self, kind: str) -> None:
        self._kind = kind

    def _data(self) -> dict[str, str]:
        registry = load_registry()
        return registry.state_to_pack() if self._kind == "state" else registry.code_to_pack()

    def __getitem__(self, key: str) -> str:
        return self._data()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def __repr__(self) -> str:
        return repr(self._data())
