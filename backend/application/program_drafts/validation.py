"""Validate a draft's documents: the same rules as a committed pack, plus the rules only a draft can break. [F05.3, ADR-013]

Documents are validated in memory with `validate_document` (the CLI's validator), never written to a folder. On top of the
schema and the supported-model checks this adds what must hold before anyone is asked to review: the code, state and names
agree across documents; the program is not already registered; and every number has a cited source, with no `TODO` left.
A draft that passes is *valid*, not *verified*: `_prototype_verify` flags are counted and reported, and review does not clear them.
"""
from __future__ import annotations

from typing import Any, Iterator

from application.program_drafts.naming import pack_file_name, year_file_name
from domain.program_drafts import CODE_PATTERN, MAX_DOCUMENT_CHARS, ProgramDraft, canonical_json
from tools.pack_validation import Report, validate_document

#: Findings kept in the stored result. Counts are always exact; this only bounds the stored list.
MAX_STORED_FINDINGS = 40
_ORDER = {"error": 0, "warning": 1, "info": 2}


def _placeholders(node: Any, path: str = "") -> Iterator[str]:
    """Paths of every string that still starts with `TODO`: scaffolding the author has not replaced."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _placeholders(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _placeholders(value, f"{path}/{i}")
    elif isinstance(node, str) and node.strip().upper().startswith("TODO"):
        yield path


def _cited(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not value.strip().upper().startswith("TODO")


def _tag(report: Report, where: str) -> list[dict[str, str]]:
    return [{"file": where, "severity": i.severity, "code": i.code, "path": i.path, "message": i.message} for i in report.issues]


def _error(where: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"file": where, "severity": "error", "code": code, "path": path, "message": message}


def _identity(draft: ProgramDraft) -> list[dict[str, str]]:
    """The code, state and registry rules for the draft as a whole."""
    from tools.program_registry import load_registry

    out: list[dict[str, str]] = []
    pack = draft.pack or {}
    if not CODE_PATTERN.match(draft.proposed_code):
        out.append(_error("draft", "code_format", "proposed_code", "a program code is upper case letters, digits and underscores, starting with a letter"))
    registry = load_registry()
    if registry.get(draft.proposed_code) is not None:
        out.append(_error("draft", "code_registered", "proposed_code", f"{draft.proposed_code} is already in the program registry"))
    if any(e.pack_file == pack_file_name(draft) for e in registry.entries):
        out.append(_error("draft", "pack_file_registered", "proposed_code", f"{pack_file_name(draft)} is already a registered pack file"))
    if (pack.get("credit") or {}).get("code") != draft.proposed_code:
        out.append(_error("pack", "code_mismatch", "credit/code", f"credit.code must be {draft.proposed_code}"))
    if (pack.get("jurisdiction") or {}).get("code") != draft.state:
        out.append(_error("pack", "state_mismatch", "jurisdiction/code", f"jurisdiction.code must be {draft.state}"))
    return out


def _year_rules(draft: ProgramDraft, key: str, doc: dict[str, Any]) -> list[dict[str, str]]:
    where = f"year {key}"
    out: list[dict[str, str]] = []
    if str(doc.get("tax_year")) != key:
        out.append(_error(where, "year_mismatch", "tax_year", f"tax_year must be {key}: a year pack is authored for its own year and never inherited"))
    for block in ("credit", "jurisdiction"):
        if (doc.get(block) or {}).get("code") != ((draft.pack or {}).get(block) or {}).get("code"):
            out.append(_error(where, "year_pack_mismatch", f"{block}/code", f"{block}.code differs from the base pack"))
    if not _cited((doc.get("_year_provenance") or {}).get("source")):
        out.append(_error(where, "citation_missing", "_year_provenance/source", "name the primary source this year's values come from; no value is accepted without one"))
    return out


def _per_document(draft: ProgramDraft) -> list[dict[str, str]]:
    """Rules that apply to each document alone: scaffolding left in, and a verification claim."""
    found: list[dict[str, str]] = []
    for where, doc in (("pack", draft.pack), *((f"year {k}", d) for k, d in sorted(draft.years.items()))):
        found += [_error(where, "todo_placeholder", p, "still holds scaffolding text: replace it with a cited value") for p in _placeholders(doc)]
        if isinstance(doc, dict) and "_verified" in doc:
            found.append(_error(where, "verified_claim", "_verified", "a draft cannot claim _verified: verification is a person checking the primary source after the files are committed"))
    return found


def _documents(draft: ProgramDraft) -> list[dict[str, str]]:
    if draft.pack is None:
        return [_error("pack", "pack_missing", "", "the draft has no base pack yet")]
    found = _tag(validate_document(draft.pack, pack_file_name(draft), "base", bool(draft.years)), "pack")
    if not _cited((draft.pack.get("credit") or {}).get("statutory_citation")):
        found.append(_error("pack", "citation_missing", "credit/statutory_citation", "cite the statute this credit comes from"))
    for key, doc in sorted(draft.years.items()):
        found += _tag(validate_document(doc, year_file_name(key), "year", True), f"year {key}")
        found += _year_rules(draft, key, doc) if isinstance(doc, dict) else []
    if not draft.years:
        found.append({"file": "draft", "severity": "warning", "code": "no_years", "path": "years",
                      "message": "no year pack: the program would be described, not calculable, until a year is authored (ADR-005)"})
    return found + _per_document(draft)

def validate_draft(draft: ProgramDraft) -> dict[str, Any]:
    """The full validation result: exact counts, every finding (errors first), and the content hash it covered."""
    findings = sorted(_identity(draft) + _documents(draft), key=lambda f: (_ORDER[f["severity"]], f["file"], f["path"]))
    counts = {s: sum(f["severity"] == s for f in findings) for s in _ORDER}
    return {
        "content_sha256": draft.content_sha256, "valid": counts["error"] == 0, "errors": counts["error"],
        "warnings": counts["warning"], "infos": counts["info"], "findings": findings, "truncated": False,
        "verification": "not_verified",
    }


def for_storage(result: dict[str, Any]) -> dict[str, Any]:
    """The result as stored: findings are shortened and capped (the counts stay exact) until it fits one column."""
    kept = [{**f, "message": f["message"][:160]} for f in result["findings"][:MAX_STORED_FINDINGS]]
    stored = {**result, "findings": kept, "truncated": len(result["findings"]) > len(kept)}
    while kept and len(canonical_json(stored)) > MAX_DOCUMENT_CHARS:
        kept.pop()
        stored["truncated"] = True
    return stored