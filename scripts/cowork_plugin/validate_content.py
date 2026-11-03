"""Content checks: every tool a skill names exists, and nothing shipped names a customer. [CH-10]

A skill is instructions to a model, and an instruction that names a tool the server
does not offer fails at the worst moment: in front of a user, mid-workflow. So the tool
names in a skill are checked against the catalog the gateway serves. A backticked
name is a tool reference when it is a catalog name, or when it wears a catalog family
prefix (`client_`, `claim_`, ...) without being a field the schemas define; the second
case is how a typo or a renamed tool is caught instead of ignored.

Writes are a pair. A skill that names `x_prepare` and never `x_commit` (or the
reverse) teaches a half-flow, which is either a preview nobody can act on or a commit
with no confirmation, so the pairing is checked per skill, references included.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from cowork_plugin.findings import WARNING, Finding
from cowork_plugin.manifest import BACKEND
from cowork_plugin.settings import ZERO_GUID

_TOKEN = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+|simulate)`")
_GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_FIELD_SUFFIXES = ("_id", "_name", "_token", "_key", "_sha256", "_version", "_usd", "_year", "_code", "_path", "_context")
_ENVELOPE_FIELDS = frozenset({"run_id", "client_id", "tax_year", "program_code"})
# Stable error codes a skill may quote; they wear a tool-family prefix without being tools.
_ERROR_CODES = frozenset({"client_not_found", "client_not_authorized"})
_TEXT = (".md", ".json", ".svg", ".txt")
SAFE_EMAIL_DOMAINS = frozenset({"example.com", "example.org", "example.net"})


def _catalog() -> Any:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from application.capabilities import catalog

    return catalog


def _property_names(node: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            names |= {key} if key not in ("type", "properties") else set()
            names |= _property_names(value)
    elif isinstance(node, list):
        for item in node:
            names |= _property_names(item)
    return names


def tool_references(text: str) -> set[str]:
    """Every backticked tool-shaped name in `text`."""
    return set(_TOKEN.findall(text))


def _skill_texts(files: dict[str, bytes]) -> dict[str, str]:
    """Skill name to the text of its SKILL.md and every companion Markdown file."""
    grouped: dict[str, list[str]] = {}
    for name, data in sorted(files.items()):
        parts = name.split("/")
        if parts[0] == "skills" and len(parts) > 2 and name.endswith(".md"):
            grouped.setdefault(parts[1], []).append(data.decode("utf-8"))
    return {skill: "\n".join(chunks) for skill, chunks in grouped.items()}


def _classify(skill: str, tokens: set[str], catalog: Any) -> list[Finding]:
    fields = _property_names([spec.schema for spec in catalog.CATALOG]) | _ENVELOPE_FIELDS | _ERROR_CODES
    families = {spec.name.split("_")[0] for spec in catalog.CATALOG}
    found: list[Finding] = []
    for token in sorted(tokens):
        spec = catalog.BY_NAME.get(token)
        if spec is None:
            if token.split("_")[0] in families and token not in fields and not token.endswith(_FIELD_SUFFIXES):
                found.append(Finding("TCC-T001", f"skills/{skill}", f"names `{token}`, which is not in the tool catalog"))
        elif not spec.implemented:
            found.append(Finding("TCC-T002", f"skills/{skill}", f"names `{token}`, which is declared but not implemented"))
        elif spec.name not in {s.name for s in catalog.offered()}:
            found.append(Finding("TCC-T002", f"skills/{skill}", f"names `{token}`, which is plumbing and is not offered to callers"))
    return found


def _pairs(skill: str, tokens: set[str]) -> list[Finding]:
    prepared = {t[: -len("_prepare")] for t in tokens if t.endswith("_prepare")}
    committed = {t[: -len("_commit")] for t in tokens if t.endswith("_commit")}
    return [
        Finding("TCC-T003", f"skills/{skill}", f"names `{stem}_{'prepare' if stem in prepared else 'commit'}` without its pair")
        for stem in sorted(prepared ^ committed)
    ]


def validate_tools(files: dict[str, bytes]) -> list[Finding]:
    """Tool references and write pairs, per skill."""
    catalog, found = _catalog(), []
    for skill, text in _skill_texts(files).items():
        tokens = tool_references(text)
        found += _classify(skill, tokens, catalog) + _pairs(skill, tokens)
    return found


def _deny_terms() -> list[tuple[str, re.Pattern[str]]]:
    """The white-label deny-list, read from `scripts/audit-export.py` so it is spelled out in one place."""
    path = Path(__file__).resolve().parents[1] / "audit-export.py"
    if not path.is_file():
        return []
    spec = importlib.util.spec_from_file_location("_audit_export_terms", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return list(getattr(module, "DENY_TERMS", []))


def validate_neutrality(files: dict[str, bytes], *, allow: frozenset[str] = frozenset()) -> list[Finding]:
    """No customer name, tenant or object id, or real address in any shipped text file."""
    terms, found = _deny_terms(), []
    if not terms:
        found.append(Finding("TCC-N000", "scripts/audit-export.py", "the deny-list could not be read; the check ran without it", WARNING))
    for name, data in sorted(files.items()):
        if not name.endswith(_TEXT):
            continue
        text = data.decode("utf-8", errors="replace")
        found += [Finding("TCC-N001", name, f"contains the deny-listed term {term!r}") for term, pattern in terms if pattern.search(text)]
        found += [Finding("TCC-N002", name, f"contains an identifier ({g}); use a placeholder") for g in sorted(set(_GUID.findall(text)))
                  if g.lower() != ZERO_GUID and g.lower() not in allow]
        found += [Finding("TCC-N003", name, f"contains an address on {d}") for d in sorted({m.lower() for m in _EMAIL.findall(text)} - SAFE_EMAIL_DOMAINS)]
    return found
