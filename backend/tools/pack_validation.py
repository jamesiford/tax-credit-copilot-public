"""Validate rule packs: JSON Schema for shape, then the semantic rules a schema cannot say. [ADR-013, ADR-005]

Used by the CLI (`scripts/validate-rule-pack.py`), the tests and, later, the portal. It checks that a pack is
well-formed and consistent with the registry and with the engine's supported models. It never says a value is legally
correct: a pack that passes is *valid*, not *verified*, and the `_prototype_verify` flags it carries are reported.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

from domain.calculation.onezero import OneZeroMethodology
from domain.programs import SUPPORTED_CREDIT_MODELS
from tools.program_registry import load_registry, rules_dir

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "rules" / "schema" / "rule-pack.schema.json"


@dataclass(frozen=True)
class Issue:
    """One finding. `error` fails validation; `warning` and `info` are reported."""

    severity: str
    code: str
    path: str
    message: str


@dataclass
class Report:
    """The findings for one file."""

    file: str
    kind: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def add(self, severity: str, code: str, message: str, path: str = "") -> None:
        self.issues.append(Issue(severity, code, path, message))


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def schema_version() -> int:
    return int(load_schema()["schema_version"])


def _subschema(kind: str) -> dict[str, Any]:
    schema = load_schema()
    return {**schema, "$ref": "#/$defs/year_pack" if kind == "year" else "#/$defs/base_pack"}


def check_schema(pack: Any, kind: str, report: Report) -> None:
    """Structural errors, one per violation, each naming the path inside the pack."""
    validator = jsonschema.Draft202012Validator(_subschema(kind))
    for err in sorted(validator.iter_errors(pack), key=lambda e: list(e.absolute_path)):
        report.add("error", "schema", err.message[:300], "/".join(str(p) for p in err.absolute_path))


def _flags(node: Any, path: str = "") -> list[str]:
    """Paths of every `_prototype_verify: true` flag in the pack."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}/{key}"
            if key == "_prototype_verify" and value is True:
                found.append(path or "/")
            found.extend(_flags(value, here))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_flags(value, f"{path}/{i}"))
    return found


def _check_models(pack: dict[str, Any], kind: str, years_authored: bool, report: Report) -> None:
    benefit = pack.get("benefit") or {}
    if "amount_per_qualifying_job_pct_of_wages" in benefit:
        # Describable today (a pack may record the statute), but the engine prices only a flat per-job amount.
        severity = "error" if kind == "year" or years_authored else "warning"
        report.add(severity, "unsupported_credit_model",
                   f"percentage-of-wages benefit is not a supported credit model ({', '.join(SUPPORTED_CREDIT_MODELS)}); "
                   "it needs engine work before this program can be priced", "benefit")
    oz = pack.get("one_zero") or {}
    try:
        OneZeroMethodology.from_pack_json(oz.get("methodology"))
    except ValueError as exc:
        report.add("error", "unsupported_methodology", str(exc), "one_zero/methodology")


def _check_thresholds(pack: dict[str, Any], report: Report) -> None:
    oz = pack.get("one_zero") or {}
    by_year = oz.get("thresholds_by_year") or {}
    year = pack.get("tax_year")
    block = by_year.get(str(year)) if year is not None else None
    if block:
        for key in ("min_weekly_hours", "min_weekly_wages"):
            if key in block and block[key] != oz.get(key):
                report.add("error", "thresholds_by_year", f"{key} {block[key]} for {year} disagrees with the pack's own {oz.get(key)}",
                           f"one_zero/thresholds_by_year/{year}/{key}")


def _check_verified_claim(pack: dict[str, Any], report: Report) -> None:
    """A pack may claim `_verified: true` only with no outstanding flag and with its sources named."""
    if pack.get("_verified") is not True:
        return
    for path in _flags(pack):
        report.add("error", "verified_with_flags", "claims _verified but still carries _prototype_verify", path)
    if not (pack.get("credit") or {}).get("statutory_citation") or not (pack.get("_year_provenance") or {}).get("source"):
        report.add("error", "verified_without_citation", "a verified pack needs credit.statutory_citation and _year_provenance.source")


def _check_names(name: str, pack: dict[str, Any], kind: str, report: Report) -> None:
    j = pack.get("jurisdiction") or {}
    if kind == "year":
        if name.split(".")[0] != str(pack.get("tax_year")):
            report.add("error", "filename", f"{name} must be named for its tax_year ({pack.get('tax_year')}.json)")
        return
    expected = "federal_" if j.get("level") == "federal" else f"{str(j.get('code', '')).lower()}_"
    if not name.startswith(expected):
        report.add("error", "filename", f"{name} must start with {expected!r} for a {j.get('level')} pack")


def validate_document(pack: Any, name: str, kind: str, years_authored: bool = False, file: str = "") -> Report:
    """Validate one pack held in memory, as it would be named on disk (`name`, e.g. `zz_demo.json` or `2025.json`).

    The portal validates a draft's documents with this and never writes them to a folder; `validate_pack` reads a file
    and calls it, so a draft and a committed pack are judged by exactly the same rules.
    """
    report = Report(file=file or name, kind=kind)
    check_schema(pack, kind, report)
    if isinstance(pack, dict):
        _check_names(name, pack, kind, report)
        _check_models(pack, kind, years_authored, report)
        _check_thresholds(pack, report)
        _check_verified_claim(pack, report)
        for flagged in _flags(pack):
            report.add("info", "unverified", "carries _prototype_verify: not verified", flagged)
    return report


def validate_pack(path: Path, years_authored: bool = False) -> Report:
    """Validate one base pack or year pack file (a year pack is a `<program>/<year>.json`)."""
    kind = "year" if path.stem.split(".")[0].isdigit() else "base"
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report = Report(file=str(path), kind=kind)
        report.add("error", "unreadable", f"cannot read as JSON: {exc}")
        return report
    return validate_document(pack, path.name, kind, years_authored, str(path))



def _load_dict(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _year_report(path: Path, base: dict[str, Any] | None) -> Report:
    report = validate_pack(path, years_authored=True)
    year = _load_dict(path)
    if base is not None and year is not None:
        for key in ("credit", "jurisdiction"):
            if (year.get(key) or {}).get("code") != (base.get(key) or {}).get("code"):
                report.add("error", "year_pack_mismatch", f"{key}.code differs from the base pack")
    return report


def _registry_checks(report: Report, name: str, base: dict[str, Any] | None, registered: dict, seen: dict[str, str]) -> None:
    """Cross-registry rules for one base pack: it is listed, its code is unique and it matches its entry."""
    if name not in registered:
        report.add("error", "unregistered", f"{name} is not listed in the program registry")
    code = ((base or {}).get("credit") or {}).get("code")
    if not code:
        return
    if code in seen:
        report.add("error", "duplicate_code", f"credit code {code} is already used by {seen[code]}")
    seen[code] = name
    entry = registered.get(name)
    if entry is not None and entry.code != code:
        report.add("error", "registry_mismatch", f"registry says {entry.code}, pack says {code}")


def validate_all(directory: Path | None = None) -> list[Report]:
    """Every base pack, year pack and the registry itself under a rules folder."""
    root = directory or rules_dir()
    registered = {e.pack_file: e for e in load_registry().entries}
    seen: dict[str, str] = {}
    reports: list[Report] = []
    for path in sorted(root.glob("*.json")):
        years = sorted(p for p in (root / path.stem).glob("*.json") if p.stem.isdigit())
        report = validate_pack(path, years_authored=bool(years))
        base = _load_dict(path)
        _registry_checks(report, path.name, base, registered, seen)
        reports.append(report)
        reports.extend(_year_report(p, base) for p in years)
    return reports
