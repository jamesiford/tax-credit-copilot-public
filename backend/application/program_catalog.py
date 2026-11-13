"""The program catalog: what the platform knows, what it can calculate and why not. [F05.1, ADR-013]

Built on the registry (`tools/program_registry`) and the authored year packs, so it cannot disagree with the engine about
which programs exist or which are calculable. `client_book.programs()` and `/api/rules` keep answering as before; this is
the richer, typed read the Programs page and the channel capability use.

Nothing here says a program's statute is verified. A pack that validates is *valid*, not *verified*: every row carries
`verification: not_verified`, the years whose pack still has `_prototype_verify`, and the validator's findings. [ADR-005]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from application.client_book import is_placeholder_year
from domain.programs import ProgramEntry
from tools.credit_math import _load_pack, authored_years
from tools.pack_validation import validate_pack
from tools.program_registry import load_registry, rules_dir

log = logging.getLogger(__name__)

#: Said on every row: the catalog reports what is encoded, never that it is right.
VERIFICATION_NOTE = (
    "Not verified. A rule pack that validates is well-formed, not legally correct: a person must verify each statutory "
    "value against the primary source. [ADR-005]"
)


class UnknownProgram(LookupError):
    """No program with that code is in the registry."""


def _reason(entry: ProgramEntry, status: str, years: list[int]) -> str:
    """Why a program cannot be run, or "" when it can."""
    if entry.level == "federal":
        return "A federal program has no state, and a run prices a state's payroll rows: federal programs are described, not calculable."
    if status == "retired":
        return "Retired: the engine no longer resolves this program."
    if status == "draft":
        return "Draft: registered for authoring only. It becomes calculable when a human commits an authored year pack and sets it described."
    if not years:
        return f"No year-scoped rule packs authored for {entry.code}. ADR-005: statute is not inherited across years."
    return ""


def _years_of(entry: ProgramEntry) -> list[int]:
    return authored_years(entry.pack_file) if (rules_dir() / entry.pack_file).is_file() else []


def _engagement_counts() -> dict[str, dict[str, int]] | None:
    """Clients per program and scope, from the batched engagement read; None when the claims store cannot answer."""
    from application.client_book import clients
    from application.services import ServiceNotBound, get_claim_repository, resolve

    try:
        ids = sorted(int(c["account_id"]) for c in clients())
        found = resolve("engagement_batch").read(get_claim_repository(), ids) or {}
    except ServiceNotBound:
        return None
    except Exception as exc:  # noqa: BLE001 - a catalog without counts is still a catalog; say so rather than fail
        log.warning("program catalog: engagement counts unavailable (%s)", type(exc).__name__)
        return None
    counts: dict[str, dict[str, int]] = {}
    for items in found.values():
        for e in items:
            bucket = counts.setdefault(e.program_code, {})
            bucket[e.scope.value] = bucket.get(e.scope.value, 0) + 1
    return counts


def _row(entry: ProgramEntry, counts: dict[str, dict[str, int]] | None) -> dict[str, Any]:
    years = _years_of(entry)
    status = entry.status(years)
    calculable = status == "calculable" and entry.level != "federal"
    unverified = [y for y in years if is_placeholder_year(entry.code, y)]
    engaged = None if counts is None else counts.get(entry.code, {})
    return {
        "code": entry.code, "name": entry.name, "state": entry.state,
        "jurisdiction": {"level": entry.level, "code": entry.jurisdiction_code},
        "lifecycle": status, "authored_years": years, "unverified_years": unverified,
        "verification": "not_verified", "calculable": calculable,
        "not_calculable_reason": "" if calculable else _reason(entry, status, years),
        "engagement": None if engaged is None else {"in_scope": engaged.get("in_scope", 0), "out_of_scope": engaged.get("out_of_scope", 0),
                                                    "prospective": engaged.get("prospective", 0), "clients": sum(engaged.values())},
    }


def list_catalog() -> dict[str, Any]:
    """Every registered program (retired ones too, labelled), in registry order, with a note that none is verified."""
    counts = _engagement_counts()
    rows = [_row(e, counts) for e in load_registry().entries]
    return {"programs": rows, "total": len(rows), "engagement_available": counts is not None, "verification_note": VERIFICATION_NOTE}


def _issues(path: Path, years_authored: bool) -> list[dict[str, str]]:
    report = validate_pack(path, years_authored=years_authored)
    return [{"severity": i.severity, "code": i.code, "path": i.path, "message": i.message} for i in report.issues]


def _year_status(entry: ProgramEntry, year: int) -> dict[str, Any]:
    path = rules_dir() / Path(entry.pack_file).stem / f"{year}.json"
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pack = {}
    return {
        "tax_year": year, "rule_pack_version": pack.get("rule_pack_version"), "unverified": is_placeholder_year(entry.code, year),
        "source": (pack.get("_year_provenance") or {}).get("source"), "issues": _issues(path, True),
    }


def _blockers(row: dict[str, Any], validation_errors: int) -> list[str]:
    out = [row["not_calculable_reason"]] if row["not_calculable_reason"] else []
    if validation_errors:
        out.append(f"{validation_errors} validation error(s) in the pack files: see the validation results.")
    return out


def catalog_detail(code: str) -> dict[str, Any]:
    """One program: its row, pack metadata, per-year status, validation results and what blocks calculation."""
    entry = load_registry().get(code)
    if entry is None:
        raise UnknownProgram(code)
    row = _row(entry, _engagement_counts())
    path = rules_dir() / entry.pack_file
    try:
        pack = _load_pack(entry.pack_file)
    except FileNotFoundError:
        pack = {}
    years = [_year_status(entry, y) for y in row["authored_years"]]
    base_issues = _issues(path, bool(years)) if path.is_file() else []
    errors = sum(i["severity"] == "error" for i in base_issues) + sum(i["severity"] == "error" for y in years for i in y["issues"])
    credit = pack.get("credit") or {}
    return {
        **row,
        "pack": {"file": entry.pack_file, "present": path.is_file(), "rule_pack_version": pack.get("rule_pack_version"),
                 "credit_name": credit.get("name"), "citation": credit.get("statutory_citation"),
                 "engine_profile": {"credit_model": entry.engine_profile.credit_model, "headcount_model": entry.engine_profile.headcount_model},
                 "notes": entry.notes},
        "years": years, "validation": {"pack": base_issues, "error_count": errors, "valid": errors == 0},
        "blockers": _blockers(row, errors),
    }
