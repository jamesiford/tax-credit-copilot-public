"""Scaffolding for a new program: a draft registry entry, a base pack and year-pack skeletons. [ADR-013]

Every statutory value in a skeleton is `null` and every block carries `_prototype_verify: true`, so a skeleton fails
validation until a person fills it in from a cited source; the validator's error list is the author's checklist. The
year skeleton is written as `<year>.draft.json`, which the engine does not read (`authored_years` counts only
`<year>.json`), so a half-filled file can never make a program look calculable. Renaming it is the human step. [ADR-005]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.programs import RegistryError
from tools.program_registry import load_registry, rules_dir

_TODO = "TODO: fill from a cited source; not verified"


def _flagged(**fields: Any) -> dict[str, Any]:
    return {"_prototype_verify": True, **fields}


def base_pack(code: str, state: str, name: str) -> dict[str, Any]:
    """A base pack with every statutory value `null` and flagged."""
    return {
        "_prototype_verification": "DRAFT skeleton. No value here is verified. Fill every null from a cited source, validate, "
                                   "then have it reviewed before any real client use.",
        "rule_pack_version": "0.0.1",
        "jurisdiction": {"level": "state", "code": state, "name": name},
        "credit": {"code": code, "name": name, "statutory_citation": _TODO},
        "tax_year_convention": _flagged(label=None, regulation=None),
        "filing": _flagged(window=_TODO, cycle="annual"),
        "thresholds": _flagged(minimum_new_jobs=None),
        "benefit": _flagged(amount_per_qualifying_job_usd=None, benefit_period_years=None, carryforward_years=None, currency="USD"),
        "one_zero": _flagged(min_weekly_hours=None, min_weekly_wages=None, wage_basis="regular", geographic_granularity="statewide",
                             pt_aggregation=False, headcount_unit_field="Worksite_ID", entity_combination="permitted"),
    }


def year_pack(base: dict[str, Any], year: int) -> dict[str, Any]:
    """A complete year skeleton for the program's identity only.

    Built from the empty skeleton, not from the base pack's values: a year's statute is authored for that year and
    never inherited from another, so no number or note is copied across. [ADR-005]
    """
    credit, jurisdiction = base["credit"], base["jurisdiction"]
    pack = base_pack(credit["code"], jurisdiction["code"], jurisdiction["name"])
    pack["credit"]["name"] = credit["name"]
    pack["jurisdiction"]["level"] = jurisdiction["level"]
    pack["tax_year"] = year
    pack["rule_pack_version"] = f"0.0.1+ty{year}"
    pack["_year_provenance"] = {"source": _TODO, "adr": "ADR-005"}
    return pack


def registry_entry(code: str, state: str, name: str, pack_file: str) -> dict[str, Any]:
    return {"code": code, "name": name, "jurisdiction": {"level": "state", "code": state}, "state": state, "pack_file": pack_file,
            "lifecycle": "draft", "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"},
            "notes": "Scaffolded draft: not verified."}


def create_program(code: str, state: str, name: str, slug: str, directory: Path | None = None, dry_run: bool = False) -> list[str]:
    """Write the base pack and add a `draft` registry entry. Returns the paths it wrote (or would write)."""
    root = directory or rules_dir()
    state = state.upper()
    pack_file = f"{state.lower()}_{slug.lower()}.json"
    registry = load_registry()
    if registry.get(code) or any(e.pack_file == pack_file for e in registry.entries):
        raise RegistryError(f"program {code} or pack {pack_file} already exists")
    if (root / pack_file).exists():
        raise RegistryError(f"{root / pack_file} already exists; nothing was written")
    wrote = [str(root / pack_file), str(registry.source)]
    if dry_run:
        return wrote
    (root / pack_file).write_text(json.dumps(base_pack(code, state, name), indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(registry.source.read_text(encoding="utf-8"))
    manifest["programs"].append(registry_entry(code, state, name, pack_file))
    registry.source.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return wrote


def create_year(pack_file: str, year: int, directory: Path | None = None, dry_run: bool = False) -> str:
    """Write `<program>/<year>.draft.json` beside any authored years; refuses to overwrite."""
    root = directory or rules_dir()
    source = root / pack_file
    if not source.is_file():
        raise RegistryError(f"{source} not found")
    target = root / Path(pack_file).stem / f"{year}.draft.json"
    if target.exists() or target.with_name(f"{year}.json").exists():
        raise RegistryError(f"{target.name} or {year}.json already exists; nothing was written")
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        base = json.loads(source.read_text(encoding="utf-8"))
        target.write_text(json.dumps(year_pack(base, year), indent=2) + "\n", encoding="utf-8")
    return str(target)
