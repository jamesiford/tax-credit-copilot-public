"""The checklist a human follows to commit an exported program, written into the bundle. [F05.5, ADR-005, ADR-013]

Plain text with no values of its own: it names the files, the tests to add, the changelog line and who must verify the statute.
Wording never says the values are verified; the first item is that a person must verify each against the primary source.
"""
from __future__ import annotations

from domain.program_drafts import ProgramDraft


def changelog_line(draft: ProgramDraft) -> str:
    years = ", ".join(sorted(draft.years)) or "no authored year yet"
    return (f"- Added program `{draft.proposed_code}` ({draft.name}, {draft.state}): rule pack and year packs for {years}. "
            "Statute values are not verified until a person verifies each against the primary source; the program is "
            "calculable only for authored years. Operators: deploy this release; no settings or migrations.")


def checklist(draft: ProgramDraft, files: list[str], pack_file: str) -> str:
    """The commit checklist as Markdown, for the bundle. It states the steps and names no value as verified."""
    year_files = [f for f in files if f.startswith("rules/") and f.count("/") == 2]
    lines = [
        f"# Commit checklist: {draft.proposed_code} ({draft.name})",
        "",
        "This bundle is a PROPOSAL. Nothing in it is verified, and importing it into a deployment does nothing until the files are",
        "committed and deployed (ADR-005). Statute stays human-authored and version controlled.",
        "",
        "## 1. Who must verify the statute (before anything else)",
        "- [ ] A qualified person who is neither the author nor the reviewer of the draft checks EVERY statutory value in every file",
        "      against the primary source (the statute or the authority's published guidance), and records the source in",
        "      `credit.statutory_citation` and each year's `_year_provenance.source`.",
        "- [ ] Only then remove the `_prototype_verify` flags they confirmed. Do not add `_verified` to a pack from this bundle.",
        "",
        "## 2. Put the files in the repository",
        *[f"- [ ] `{f}` -> `backend/{f}`" for f in files if f.startswith("rules/")],
        f"- [ ] Add the entry in `registry-patch.json` to `backend/rules/registry/programs.json` (lifecycle stays `described`; `calculable` is",
        "      derived from authored year packs and is never typed).",
        "",
        "## 3. Tests to add (customer-neutral, fictional or published values only)",
        f"- [ ] `backend/tests/test_{draft.proposed_code.lower()}_pack.py`: `validate_all()` reports no error for `{pack_file}` and its years.",
        f"- [ ] A pricing test at hand-computed inputs taken from the cited source (not from this tool's output) for each of: "
        f"{', '.join(sorted(draft.years)) or 'each authored year'}.",
        "- [ ] The program appears in `GET /api/v2/programs` as calculable for exactly its authored years, and is selectable in the",
        "      run dialog and the engagement controls with no frontend change.",
        "",
        "## 4. Changelog (same commit)",
        changelog_line(draft),
        "",
        "## 5. Gates and deploy",
        "- [ ] `python scripts/validate-rule-pack.py`, the backend fast gate, the full backend suite, the frontend tests and build.",
        "- [ ] Commit, review and deploy the normal way (`azd up`). There is no database switch and no runtime toggle: the program becomes",
        "      calculable when the deployed rules folder holds its year packs.",
        "",
        f"Year packs in this bundle: {', '.join(year_files) if year_files else 'none (the program will be described, not calculable)'}.",
        "",
    ]
    return "\n".join(lines)
