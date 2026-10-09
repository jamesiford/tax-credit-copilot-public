"""Assemble the Reference Dataset approval package for the partner.

Produces a single folder James can send: the Step 1 and One/Zero outputs, the
rules that produced them, and a cover sheet stating exactly what is verified
against the partner's own figures and what is not.

    cd backend
    python -m tools.build_approval_package
    python -m tools.build_approval_package --out "C:/path/to/folder"

The cover sheet is the point. Our control totals match the partner's reported figures
exactly; our **eligible employee lists have never been compared to the partner's**,
because the partner has not supplied them. Sending an approval package that blurs those
two would invite a sign-off on something nobody has checked.

Confidentiality: the outputs carry surrogate employee IDs from the source
extract. They contain no names, SSNs or addresses, but they are the partner's
client payroll and go back only to the partner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_OUTPUT = _BACKEND / "data" / "reference_output"
_RULES = _BACKEND / "rules" / "ga_jtc"
_METHODOLOGY = _BACKEND / "rules" / "methodology"

# Files the partner needs to reproduce or check our result, and nothing else.
_RESULT_FILES = [
    "step1_summary.json",
    "common_employee_totals.csv",
    "min_max_eligibility.csv",
    "pay_period_eligibility.csv",
    "eligibility_discrepancies.csv",
    "onezero_summary.json",
    "min_max_onezero_summary.csv",
    "pay_period_onezero_summary.csv",
    "min_max_onezero_matrix.csv",
    "pay_period_onezero_matrix.csv",
    "onezero_overlap_flags.json",
    "source_manifest.json",
]

_RULE_FILES = [
    (_METHODOLOGY / "reference-dataset-assumptions.v8.json", "rules/methodology-v8.json"),
    (_METHODOLOGY / "reference-onezero-assumptions.v7.json", "rules/onezero-methodology-v7.json"),
    (_RULES / "2023.json", "rules/ga-jtc-statute-2023.json"),
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_summary() -> dict:
    from tools.reference_workspace import ReferenceWorkspaceService

    return ReferenceWorkspaceService().summary()


def _control_totals() -> tuple[str, str, int]:
    """Hours, wages and employee count read back from the emitted output.

    Computed from the artifact we are actually sending rather than from the
    in-memory run: if the two ever disagreed, the number in the cover sheet
    would describe something other than the file attached to it.
    """
    import csv
    from decimal import Decimal

    path = _OUTPUT / "common_employee_totals.csv"
    hours = wages = Decimal(0)
    employees = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            employees += 1
            hours += Decimal(row["TotalHours"] or 0)
            wages += Decimal(row["TotalWages"] or 0)
    return f"{hours:,.2f}", f"${wages:,.2f}", employees


def _cover_sheet(summary: dict, manifest: list[dict]) -> str:
    src = summary["source"]["controls"]
    sel = summary["selection"]
    el = summary["eligibility"]
    inv = el["denominator_invariant"]
    run = summary["run"]
    boundary = summary["boundary"]
    statutory = el["thresholds"]

    hours, wages, employee_count = _control_totals()
    verified_rows = [
        ("Records after the fiscal trim", f"{sel['included']:,}", "384,418"),
        ("Total hours", hours, "4,950,777.43"),
        ("Total wages", wages, "$82,533,629.87"),
        ("Distinct employees", f"{employee_count:,}", "10,236"),
    ]

    lines = [
        "# Georgia JTC — Reference Dataset result for review",
        "",
        f"**Prepared** {date.today():%d %B %Y} · Microsoft, for the partner's Employer Services team",
        "",
        "---",
        "",
        "## What we are asking you to confirm",
        "",
        "Two different things, and they are at very different stages.",
        "",
        "### 1. The population — we believe this is settled",
        "",
        "Running your four payroll files through our engine reproduces the control",
        "totals from your 30 July email **exactly**:",
        "",
        "| Control | Ours | Yours |",
        "| --- | --- | --- |",
    ]
    for label, ours, theirs in verified_rows:
        match = "✅" if ours.replace(",", "").replace("$", "") == theirs.replace(",", "").replace("$", "") else "⚠️"
        lines.append(f"| {label} | {ours} | {theirs} {match} |")

    lines += [
        "",
        f"From {src['physical_rows']:,} physical rows, {src['usable_rows']:,} are usable",
        f"({src['physical_rows'] - src['usable_rows']:,} blank padding rows) and",
        f"{sel.get('excluded_pay_date_after_fy', 0)} are dropped by the fiscal trim.",
        "",
        "**Ask:** confirm the trim rule. We trim on **paycheck date only** — a row",
        "whose pay period ends after fiscal-year end is kept when its cheque date",
        "falls in the window. Did you do the same?",
        "",
        "### 2. The eligibility result — NOT yet verified against your output",
        "",
        f"We identify **{el['min_max']['eligible_employees']} employees eligible under Min-Max** and",
        f"**{el['pay_period']['eligible_employees']} under Pay Period**, from {el['employees_with_totals']:,} evaluated.",
        "",
        f"- Eligible under both methods: {el['reconciliation']['eligible_both']}",
        f"- Min-Max only: {el['reconciliation']['min_max_only']}",
        f"- Pay Period only: {el['reconciliation']['pay_period_only']}",
        "",
        "**These counts have never been compared to yours employee by employee.**",
        "Our engine records the comparison as `not_supplied`: we have your summary",
        "figures but not your eligible-employee lists, so we cannot yet say whether",
        "we agree on *which* people qualify — only that our totals are close.",
        "",
        "**This is the ask that matters.** Two lists of employee IDs — one per",
        "method — would let us reconcile name by name and close this out. Until",
        "then our position is *\"our numbers land near yours\"*, which is not the",
        "same as *\"we agree\"*.",
        "",
        "---",
        "",
        "## Standing caveats — what this result does not claim",
        "",
        "Stated rather than implied, so nothing here is a surprise later.",
        "",
    ]

    for caveat in summary["exceptions"]["step1"]:
        lines.append(f"- {caveat}")
    for caveat in summary["exceptions"]["onezero"]:
        lines.append(f"- {caveat}")

    lines += [
        "",
        "### The one worth your attention",
        "",
        f"**{inv['pay_period_gt_min_max']:,} employees** ({inv['pay_period_gt_min_max']/el['employees_with_totals']:.0%} of the population) have a",
        "Pay Period denominator **larger** than their Min-Max denominator. Your",
        "workbook treats that as impossible — Pay Period weeks should never exceed",
        "the Min-Max span.",
        "",
        f"No individual case exceeds your {inv['review_tolerance_weeks']}-week review tolerance",
        f"(largest excess is {float(inv['maximum_excess_weeks']):.2f} weeks), and we have neither capped nor",
        "repaired a single one — the figures above are what the data produced. But",
        "the count is large enough that we would rather you saw it than found it.",
        "",
        "Our reading is that it follows from the missing leading lookback below,",
        "not from a calculation error. We would value your view.",
        "",
        "### Source data gaps",
        "",
        f"- **No pre-fiscal-year payroll.** Earliest pay period starts {boundary['earliest_valid_pay_period_start']},",
        "  which is inside the window. Denominators are therefore not forced to 52",
        "  weeks and the first period of the year is short for everyone.",
        "- **November 2023 and July 2024 semi-monthly runs are absent** from the",
        "  extract. We believe this is a defect in the file rather than in either",
        "  calculation.",
        "- **No pay codes** — every supplied wage is treated as eligible",
        "  compensation. Georgia uses all remuneration, so we expect this is",
        "  harmless here, but it is an assumption rather than a fact.",
        "- **No hire or termination dates**, so no employment-period capping.",
        "",
        "---",
        "",
        "## The rules that produced this",
        "",
        "We have separated **what the statute requires** from **how we measured**,",
        "because they change for different reasons and on different schedules.",
        "",
        f"### Statute — Georgia JTC, Tax Year {statutory['source_tax_year']}",
        "",
        f"- Minimum average weekly hours: **{statutory['minimum_average_weekly_hours']:.0f}**",
        f"- Minimum average weekly wages: **${statutory['minimum_average_weekly_wages_usd']:,.0f}**",
        f"- Source: {statutory['lowest_wage_county']} County, DOL report year {statutory['dol_report_year']}",
        f"- File: `{statutory['statutory_source']}`",
        "",
        "Taken from your `JTCHistoricalWages_Jul 2025.pdf`. We hold every published",
        "year (TY2004–TY2025) so a retroactive audit runs each year under the rules",
        "in force that year rather than today's.",
        "",
        "### Methodology — 12 decisions, BA-01 to BA-12",
        "",
        "In `rules/methodology-v8.json`. Each one records the decision, the evidence",
        "behind it, and **what would prove it wrong** — that last field is there so",
        "you can disagree precisely rather than in general.",
        "",
        "The two that changed most in review:",
        "",
        "- **BA-03 — Pay Period denominator.** We sum each period's actual",
        "  inclusive span, `(PPE − PPS + 1) / 7`. We do *not* use the PayFrequency",
        "  code as a week multiplier. Using the literal constants gave 447 eligible",
        "  against your 659, so we concluded your output implies actual span.",
        "- **BA-12 — short pay periods.** Periods under 7 days are excluded from",
        "  the denominator but their hours and wages stay in the numerator. This",
        "  came from your 20 August correction.",
        "",
        "---",
        "",
        "## Reproducing this",
        "",
        "Every file below carries a SHA-256. The run is sealed: same inputs, same",
        "rules, same code commit produce identical bytes.",
        "",
        f"- Step 1 calculation: `{run['step1_calculation_id']}`",
        f"- One/Zero calculation: `{run['onezero_calculation_id']}`",
        f"- Source manifest: `{run['source_manifest_sha256']}`",
        f"- Methodology: `{run['step1_assumption_set_id']}`",
        f"- Code commit: `{run['code_commit']}`",
        "",
        "### Package contents",
        "",
        "| File | SHA-256 (first 16) |",
        "| --- | --- |",
    ]
    for entry in manifest:
        lines.append(f"| `{entry['path']}` | `{entry['sha256'][:16]}` |")

    lines += [
        "",
        "---",
        "",
        "## What we would like back",
        "",
        "1. **The two eligible-employee lists** — Min-Max and Pay Period, employee",
        "   IDs only. This is the one item that cannot be worked around.",
        "2. **Confirm or correct the twelve methodology decisions**, particularly",
        "   BA-03 and BA-12.",
        f"3. **Your read on the {inv['pay_period_gt_min_max']:,} denominator cases** — defect, or expected",
        "   given the missing lookback?",
        "4. **Whether the November and July gaps** are a known extract issue.",
        "",
        "Once we have (1), we can state agreement or disagreement precisely instead",
        "of approximately — and that is what the word *parity* should mean before",
        "any of this reaches a filed return.",
        "",
        "---",
        "",
        "*Contains the partner's client payroll under surrogate identifiers. No names,",
        "SSNs or addresses. Not for redistribution.*",
        "",
    ]
    return "\n".join(lines)


def build(out_dir: Path) -> int:
    if not _OUTPUT.exists():
        print(f"No reference output at {_OUTPUT}. Build the workspace first.", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results").mkdir(exist_ok=True)
    (out_dir / "rules").mkdir(exist_ok=True)

    manifest: list[dict] = []

    missing = []
    for name in _RESULT_FILES:
        source = _OUTPUT / name
        if not source.exists():
            missing.append(name)
            continue
        target = out_dir / "results" / name
        shutil.copy2(source, target)
        manifest.append({"path": f"results/{name}", "sha256": _sha256(target),
                         "bytes": target.stat().st_size})

    for source, rel in _RULE_FILES:
        if not source.exists():
            missing.append(str(source))
            continue
        target = out_dir / rel
        shutil.copy2(source, target)
        manifest.append({"path": rel, "sha256": _sha256(target),
                         "bytes": target.stat().st_size})

    if missing:
        print("MISSING (not packaged):", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)

    summary = _load_summary()
    (out_dir / "README.md").write_text(_cover_sheet(summary, manifest), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps({
            "prepared": date.today().isoformat(),
            "run": summary["run"],
            "files": manifest,
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    archive = out_dir.with_suffix(".zip")
    if archive.exists():
        archive.unlink()
    shutil.make_archive(str(out_dir), "zip", root_dir=out_dir.parent, base_dir=out_dir.name)

    total = sum(entry["bytes"] for entry in manifest)
    print(f"Package: {out_dir}")
    print(f"  {len(manifest)} files, {total / 1024 / 1024:.1f} MB")
    print(f"  archive: {archive.name}, {archive.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  cover sheet: README.md")
    return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(_REPO / "dist" / f"reference-dataset-review-{date.today():%Y-%m-%d}"),
    )
    args = parser.parse_args()
    return build(Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
