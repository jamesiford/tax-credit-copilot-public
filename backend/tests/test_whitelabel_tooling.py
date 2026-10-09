"""The white-label tooling itself: shape, self-exclusion, allow-list. [WL-12, B01]

These exercise the tools' logic directly rather than depending on the current
state of the tree, which changes every WP: a real baseline run (both tools in
report mode) lives in STATUS.md's decisions log for B01, not here.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("audit_export", ROOT / "scripts" / "audit-export.py")
audit_export = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_export)


def test_both_tools_exclude_internal_planning_and_themselves():
    files = audit_export.tracked_files()

    assert not any(f.startswith("docs/platform-v2/") for f in files)
    assert "AGENTS.md" not in files
    assert "scripts/check-whitelabel.ps1" not in files
    assert "scripts/audit-export.py" not in files
    assert "scripts/whitelabel-allowlist.txt" not in files


def test_every_allowlist_entry_is_for_a_frozen_or_immutable_file():
    """The allow-list started empty (B01). Every entry added since must be for
    a file this repo's own rules forbid editing — a frozen parity pin
    (AGENTS.md) or an immutable published methodology set (house rule: never
    edit a published set) — never a convenience to silence a real finding.
    """
    allow = audit_export.load_allowlist(ROOT / "scripts" / "whitelabel-allowlist.txt")

    frozen_prefixes = (
        "backend/tests/certified.py",
        "backend/rules/methodology/certified-figures.json",
        "backend/rules/methodology/reference-dataset-assumptions.v",
        "backend/rules/methodology/reference-onezero-assumptions.v",
    )
    assert allow, "no entries yet is also fine; this guards what IS there"
    for path, _term in allow:
        assert path.startswith(frozen_prefixes), (
            f"{path} is not a known frozen/immutable file — read "
            "scripts/whitelabel-allowlist.txt's justification before allowing this"
        )


def test_an_allowlisted_term_is_suppressed_and_others_are_not():
    # Use the real deny-list's own terms (never a literal copy here) so this
    # test's intent is unambiguous without adding another hit for itself to
    # find; scripts/audit-export.py is already self-excluded.
    term_a, term_b = audit_export.DENY_TERMS[0][0], audit_export.DENY_TERMS[1][0]
    allow = {("stakeholder-docs/x.docx", term_a)}

    assert audit_export.is_allowed(allow, "stakeholder-docs/x.docx", term_a)
    assert audit_export.is_allowed(allow, "STAKEHOLDER-DOCS/X.DOCX", term_a.upper())
    assert not audit_export.is_allowed(allow, "stakeholder-docs/x.docx", term_b)
    assert not audit_export.is_allowed(allow, "other.docx", term_a)


def test_a_wildcard_allowlist_entry_applies_everywhere():
    allow = {("*", "synthetic-data")}

    assert audit_export.is_allowed(allow, "any/path.csv", "synthetic-data")


def test_raster_and_pdf_are_unconditional_findings(tmp_path, monkeypatch):
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "b.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(audit_export, "ROOT", tmp_path)

    findings = audit_export.check_raster_and_pdf(["a.png", "b.svg"])

    assert [f["path"] for f in findings] == ["a.png"]
    assert findings[0]["kind"] == "raster_or_pdf"


def test_office_xml_is_scanned_for_the_deny_list(tmp_path, monkeypatch):
    term = audit_export.DENY_TERMS[0][0]
    doc = tmp_path / "note.docx"
    with zipfile.ZipFile(doc, "w") as archive:
        archive.writestr("word/document.xml", f"<w:t>Reviewed by {term.title()}</w:t>")
    monkeypatch.setattr(audit_export, "ROOT", tmp_path)

    findings = audit_export.check_office_documents(["note.docx"], allow=set())

    assert any(f["kind"] == "office_text" and term in f["detail"] for f in findings)


def test_svg_text_is_scanned_for_the_deny_list(tmp_path, monkeypatch):
    term = audit_export.DENY_TERMS[1][0]
    (tmp_path / "logo.svg").write_text(
        f"<svg><title>{term.title()} brand mark</title></svg>", encoding="utf-8",
    )
    monkeypatch.setattr(audit_export, "ROOT", tmp_path)

    findings = audit_export.check_svg_text(["logo.svg"], allow=set())

    assert any(term in f["detail"] for f in findings)


def test_csv_flags_only_the_scoped_shapes(tmp_path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "Employee_ID,Social_Security_Number,Contact_Email,Amount\n"
        "16816619,123-45-6789,jdoe@gmail.com,9995551234\n"
        "E00042,999-12-3456,jdoe@example.com,100\n",
        encoding="utf-8",
    )

    problems = audit_export._check_csv(csv_path)
    details = [p for _, p in problems]

    assert any("employee-id shape" in d for d in details)
    assert any("SSN-shaped" in d for d in details)
    assert any("email does not end in" in d for d in details)
    assert len(problems) == 3, problems


def test_json_walks_nested_objects_and_lists_with_key_context(tmp_path):
    json_path = tmp_path / "rows.json"
    json_path.write_text(json.dumps({
        "employees": [
            {"TCCEmployeeId": "16816619", "note": "fine"},
            {"TCCEmployeeId": "E00042"},
        ],
    }), encoding="utf-8")

    problems = audit_export._check_json(json_path)

    assert len(problems) == 1
    assert "employee-id shape" in problems[0][1]


def test_csv_and_json_have_zero_findings_on_clean_synthetic_data(tmp_path):
    csv_path = tmp_path / "clean.csv"
    csv_path.write_text(
        "Employee_ID,Social_Security_Number,Contact_Email\n"
        "E00001,999-00-0001,person1@example.com\n",
        encoding="utf-8",
    )

    assert audit_export._check_csv(csv_path) == []


def test_check_whitelabel_runs_clean_in_report_mode():
    """Smoke test: the tool runs to completion and exits 0 without -Enforce."""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", "scripts/check-whitelabel.ps1"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scanned" in result.stdout


def test_audit_export_runs_clean_in_report_mode():
    result = subprocess.run(
        [sys.executable, "scripts/audit-export.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scanned" in result.stdout
