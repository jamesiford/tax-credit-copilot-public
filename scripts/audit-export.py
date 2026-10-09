"""Export-readiness audit: binaries, the raster/PDF ban, and synthetic data.
[WL-12, WL-13, B01]

    python scripts/audit-export.py            # report mode (default), exits 0
    python scripts/audit-export.py --enforce  # exit 1 on any finding

Runs over every git-tracked file except `docs/platform-v2/**` (internal
planning, removed before export) and the root `AGENTS.md`:

  (a) Office documents (`.docx`/`.xlsx`/`.pptx`, which are zip archives):
      every XML/rels part is decoded and scanned for the WL-12 deny-list.
  (b) PDFs: text-extracted and scanned the same way if `pypdf` is installed.
      Otherwise a tracked PDF is a finding on its own (`pdf_unscanned`) unless
      allow-listed as `pdf-unscanned` once a human has confirmed it is
      scrubbed and regenerated.
  (c) No raster images or PDFs anywhere in the public tree (WL-13): any
      `.png/.jpg/.jpeg/.gif/.webp/.bmp/.ico/.pdf` is a finding, unconditionally
      — there is no allow-list entry for this one, because the fix is to
      delete the file, not to excuse it. SVG is allowed, and (defence in
      depth, alongside `check-whitelabel.ps1`) its text is scanned here too.
  (d) Synthetic-data validator over every `.csv`/`.json`/`.xlsx` value, scoped
      by the nearest column header / object key so a coincidental number
      doesn't become a false positive:
        - An SSN-shaped value (`###-##-####`, or bare 9 digits in a
          SSN-or-social-security-named field) must start with `9`.
        - An email-shaped value must end in `.example`, `example.com` or
          `.test`.
        - No value in an employee-named field may be bare 8-9 digits — the
          shape of the private fixture's real `TCCEmployeeId`/`Employee_ID`
          column. Synthetic data uses the `E#####` shape instead.

Uses the same allow-list as `check-whitelabel.ps1`:
`scripts/whitelabel-allowlist.txt`, `<path>|<term>|<justification>`. For this
script `<term>` is either a WL-12 deny-list term, `pdf-unscanned`, or
`synthetic-data`.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

_EXCLUDED_PREFIX = "docs/platform-v2/"
_EXCLUDED_EXACT = {"AGENTS.md"}
_SELF_EXCLUDED = {
    "scripts/check-whitelabel.ps1",
    "scripts/audit-export.py",
    "scripts/whitelabel-allowlist.txt",
}

#: WL-12's exact list. 'john' is reviewed by hand, case-sensitive, comments
#: and docs only — deliberately not an automated term (see REQUIREMENTS.md).
_DENY_WORDS = [
    "experian", "skowronski", "wiseman", "tichina", "anusha", "mohsin",
    "incentiveworks", "ehc", "bcs record", "flex_gold", "flex_ops",
    "fordjames", "MngEnvMCAP", "experian-tax-credit-demo",
]
DENY_TERMS: list[tuple[str, re.Pattern[str]]] = [
    (word, re.compile(re.escape(word), re.IGNORECASE)) for word in _DENY_WORDS
]
DENY_TERMS.append(("force ?flex", re.compile("force ?flex", re.IGNORECASE)))

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}
PDF_EXT = ".pdf"
OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}
SYNTHETIC_EXTS = {".csv", ".json", ".xlsx"}

_SSN_DASHED = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_SSN_BARE = re.compile(r"^\d{9}$")
_EMAIL = re.compile(r"^[A-Za-z0-9.+_-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
_EMPLOYEE_ID_SHAPE = re.compile(r"^\d{8,9}$")
_EMPLOYEE_KEY_HINT = re.compile(r"employee", re.IGNORECASE)
_SSN_KEY_HINT = re.compile(r"ssn|social.?security", re.IGNORECASE)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode("utf-8")
    names = [name for name in out.split("\0") if name]
    return [
        name for name in names
        if not name.startswith(_EXCLUDED_PREFIX)
        and name not in _EXCLUDED_EXACT
        and name not in _SELF_EXCLUDED
    ]


def load_allowlist(path: Path) -> set[tuple[str, str]]:
    allow: set[tuple[str, str]] = set()
    if not path.exists():
        return allow
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) >= 2:
            allow.add((parts[0].strip().lower(), parts[1].strip().lower()))
    return allow


def is_allowed(allow: set[tuple[str, str]], path: str, term: str) -> bool:
    p, t = path.lower(), term.lower()
    return ("*", t) in allow or (p, t) in allow


def check_raster_and_pdf(files: list[str]) -> list[dict[str, str]]:
    """WL-13: absolute, no allow-list entry — the fix is deletion."""
    findings = []
    for name in files:
        ext = Path(name).suffix.lower()
        if ext in RASTER_EXTS or ext == PDF_EXT:
            findings.append({
                "kind": "raster_or_pdf", "path": name,
                "detail": f"{ext} is not allowed in the public tree (WL-13)",
            })
    return findings


def _scan_office_zip(path: Path) -> list[str] | None:
    """Terms found across every XML/rels part. None if not a readable zip."""
    hits: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not (member.endswith(".xml") or member.endswith(".rels")):
                    continue
                try:
                    text = archive.read(member).decode("utf-8", errors="ignore")
                except (KeyError, OSError):
                    continue
                for term, pattern in DENY_TERMS:
                    if pattern.search(text):
                        hits.append(term)
    except (zipfile.BadZipFile, OSError):
        return None
    return hits


def check_office_documents(files: list[str], allow: set[tuple[str, str]]) -> list[dict[str, str]]:
    findings = []
    for name in files:
        if Path(name).suffix.lower() not in OFFICE_EXTS:
            continue
        hits = _scan_office_zip(ROOT / name)
        if hits is None:
            findings.append({
                "kind": "office_unreadable", "path": name,
                "detail": "could not open as a zip archive",
            })
            continue
        for term in sorted(set(hits)):
            if not is_allowed(allow, name, term):
                findings.append({
                    "kind": "office_text", "path": name,
                    "detail": f"deny-list term '{term}' found in an Office XML part",
                })
    return findings


def check_pdfs(files: list[str], allow: set[tuple[str, str]]) -> list[dict[str, str]]:
    try:
        import pypdf
        have_pypdf = True
    except ImportError:
        have_pypdf = False

    findings = []
    for name in files:
        if Path(name).suffix.lower() != PDF_EXT:
            continue
        if not have_pypdf:
            if not is_allowed(allow, name, "pdf-unscanned"):
                findings.append({
                    "kind": "pdf_unscanned", "path": name,
                    "detail": (
                        "pypdf is not installed; text not scanned. Allow-list as "
                        "'<path>|pdf-unscanned|regenerated and reviewed by hand' "
                        "once a human has confirmed it is scrubbed"
                    ),
                })
            continue
        try:
            reader = pypdf.PdfReader(str(ROOT / name))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # noqa: BLE001 — any extraction failure is a finding
            findings.append({"kind": "pdf_unreadable", "path": name, "detail": str(exc)})
            continue
        for term, pattern in DENY_TERMS:
            if pattern.search(text) and not is_allowed(allow, name, term):
                findings.append({
                    "kind": "pdf_text", "path": name,
                    "detail": f"deny-list term '{term}' found in extracted PDF text",
                })
    return findings


def check_svg_text(files: list[str], allow: set[tuple[str, str]]) -> list[dict[str, str]]:
    findings = []
    for name in files:
        if Path(name).suffix.lower() != ".svg":
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for term, pattern in DENY_TERMS:
            if pattern.search(text) and not is_allowed(allow, name, term):
                findings.append({
                    "kind": "svg_text", "path": name,
                    "detail": f"deny-list term '{term}' found in SVG text",
                })
    return findings


def _check_value(key: str | None, value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if _SSN_DASHED.match(text) and not text.startswith("9"):
        return "SSN-shaped value does not start with 9"
    if key and _SSN_KEY_HINT.search(key) and _SSN_BARE.match(text) and not text.startswith("9"):
        return "SSN-shaped value does not start with 9"

    if _EMAIL.match(text):
        lowered = text.lower()
        if not (lowered.endswith(".example") or lowered.endswith("example.com") or lowered.endswith(".test")):
            return "email does not end in .example, example.com or .test"

    if key and _EMPLOYEE_KEY_HINT.search(key) and _EMPLOYEE_ID_SHAPE.match(text):
        return "matches the private fixture's employee-id shape (bare 8-9 digits); use the E##### synthetic shape"

    return None


def _check_csv(path: Path) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                for key, value in row.items():
                    problem = _check_value(key, value)
                    if problem:
                        problems.append((f"row {row_number}, column {key}", problem))
    except OSError:
        pass
    return problems


def _check_json(path: Path) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return problems

    def walk(node: Any, key: str | None, where: str) -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, child_key, f"{where}.{child_key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, key, f"{where}[{index}]")
        else:
            problem = _check_value(key, node)
            if problem:
                problems.append((where, problem))

    walk(data, None, "$")
    return problems


def _check_xlsx(path: Path) -> list[tuple[str, str]]:
    try:
        import openpyxl
    except ImportError:
        return [("(workbook)", "openpyxl is not installed; cell values not scanned")]
    try:
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 — unreadable workbook is itself a finding
        return [("(workbook)", f"could not open: {exc}")]

    problems: list[tuple[str, str]] = []
    for sheet in workbook.worksheets:
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            continue
        headers = [str(cell) if cell is not None else "" for cell in header]
        for row_number, row in enumerate(rows, start=2):
            for col_index, value in enumerate(row):
                key = headers[col_index] if col_index < len(headers) else None
                problem = _check_value(key, value)
                if problem:
                    label = key or f"column {col_index}"
                    problems.append((f"{sheet.title}!row {row_number}, {label}", problem))
    workbook.close()
    return problems


def check_synthetic_data(files: list[str], allow: set[tuple[str, str]]) -> list[dict[str, str]]:
    findings = []
    for name in files:
        ext = Path(name).suffix.lower()
        if ext not in SYNTHETIC_EXTS:
            continue
        if is_allowed(allow, name, "synthetic-data"):
            continue
        full = ROOT / name
        if ext == ".csv":
            problems = _check_csv(full)
        elif ext == ".json":
            problems = _check_json(full)
        else:
            problems = _check_xlsx(full)
        for where, problem in problems:
            findings.append({"kind": "synthetic_data", "path": name, "detail": f"{where}: {problem}"})
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--enforce", action="store_true", help="exit 1 on any finding")
    parser.add_argument(
        "--allowlist", type=Path, default=ROOT / "scripts" / "whitelabel-allowlist.txt",
    )
    args = parser.parse_args(argv)

    allow = load_allowlist(args.allowlist)
    files = tracked_files()

    findings: list[dict[str, str]] = []
    findings += check_raster_and_pdf(files)
    findings += check_office_documents(files, allow)
    findings += check_pdfs(files, allow)
    findings += check_svg_text(files, allow)
    findings += check_synthetic_data(files, allow)

    by_kind: dict[str, int] = {}
    for item in findings:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1

    print(f"scanned {len(files)} tracked file(s) (excluding docs/platform-v2/**, AGENTS.md, tool self-reference)")
    print()
    print("by kind:")
    for kind, count in sorted(by_kind.items(), key=lambda item: -item[1]):
        print(f"  {kind:<20} {count:>5}")
    print()
    print(f"total: {len(findings)} finding(s)")

    if args.enforce and findings:
        print()
        print("FINDINGS (first 50):")
        for item in findings[:50]:
            print(f"  {item['path']}: [{item['kind']}] {item['detail']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
