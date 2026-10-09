"""Automated QC with human validation checkpoints (CALC-07 + CALC-08).

Spec: Part B/B5 + Part D/AI-02. Two checks the partner performs by eye today, now
automated — but exception-first and NEVER silently dropping a record:

* **Test of twos (CALC-07)** — an employee may not be counted at more than one
  unit in the same month. Movement between units, or a bonus paid on a second
  magical pay date, can produce a "2" (double counting). We surface every such
  case for a reviewer to resolve; we do not auto-remove.

* **Meaningful-pay-period filter (CALC-08)** — scraggly, low-value periods
  (e.g. a few dollars over a period, or a sub-weekly stray) distort the
  denominator. We flag them with their hours/wages so a reviewer can confirm;
  their value is preserved (the partner keeps the hours/wages, only drops the
  pay-period *structure*).

Everything here is pure and deterministic and records a calculation-trail row.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date
from typing import Any

from domain.calculation.trail import current_recorder

# Everything that distinguishes one payroll LINE from another. A scraggly
# anomaly is one line, and (employee, worksite, pay_date) is not a line: on the
# reference client up to six lines share it — reversals and pay-code splits
# paid the same day — so 7,365 anomalies collapsed onto 3,367 ids, and a `drop`
# resolved against one of them removed every line paid that day, including the
# real wages the reviewer never flagged.
_LINE_FIELDS = (
    "Employee_ID", "Worksite_ID", "Tax_Year", "Pay_Period_Start", "Pay_Period_End",
    "Pay_Date", "Pay_Code", "Hours_Worked", "Gross_Wages",
)


def _line_content(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in _LINE_FIELDS:
        value = row.get(field)
        if field in ("Hours_Worked", "Gross_Wages"):
            parts.append(f"{float(value or 0.0):.4f}")
        elif field in ("Pay_Period_Start", "Pay_Period_End", "Pay_Date"):
            parts.append(str(value or "")[:10])
        else:
            parts.append(str(value or ""))
    return "|".join(parts)


def pay_line_keys(rows: list[dict[str, Any]]) -> list[str]:
    """One stable key per payroll line, aligned with `rows`.

    A hash of the line's content plus its occurrence among lines with IDENTICAL
    content. The suffix is needed because the source does hold exact duplicate
    lines; which copy is "the first" does not matter, since identical lines are
    interchangeable, so the key survives a change in read order. It is a hash
    rather than the fields themselves so an employee id never reaches the
    resolve URL, which carries this key in its path.
    """
    seen: dict[str, int] = defaultdict(int)
    keys: list[str] = []
    for row in rows:
        digest = hashlib.sha256(_line_content(row).encode("utf-8")).hexdigest()[:20]
        seen[digest] += 1
        keys.append(f"{digest}.{seen[digest]}")
    return keys


def _month_key(pay_date: str) -> str:
    """YYYY-MM bucket from an ISO pay date (the 1-0 headcount month key)."""
    d = date.fromisoformat(str(pay_date)[:10])
    return f"{d.year:04d}-{d.month:02d}"


def _filter(rows: list[dict[str, Any]], tax_year: int, state: str | None) -> list[dict[str, Any]]:
    out = [r for r in rows if int(r.get("Tax_Year", 0)) == tax_year]
    if state:
        pref = f"{state.upper()}_"
        out = [r for r in out if str(r.get("Worksite_ID", "")).startswith(pref)]
    return out


def detect_test_of_twos(
    rows: list[dict[str, Any]],
    *,
    tax_year: int,
    state: str | None = None,
) -> list[dict[str, Any]]:
    """CALC-07 — employees counted at >1 unit in the same month.

    Returns one anomaly per (employee, month) that spans multiple worksites,
    with the units and the wages/hours at each so a reviewer can decide which
    unit legitimately owns the headcount. Nothing is dropped.
    """
    scoped = _filter(rows, tax_year, state)
    # (employee, month) -> {worksite -> {"wages","hours","periods"}}
    grouped: dict[tuple[str, str], dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"wages": 0.0, "hours": 0.0, "periods": 0}))
    for r in scoped:
        emp = str(r.get("Employee_ID", ""))
        month = _month_key(r.get("Pay_Date", "1900-01-01"))
        unit = str(r.get("Worksite_ID", ""))
        cell = grouped[(emp, month)][unit]
        cell["wages"] += float(r.get("Gross_Wages", 0.0) or 0.0)
        cell["hours"] += float(r.get("Hours_Worked", 0.0) or 0.0)
        cell["periods"] += 1

    anomalies: list[dict[str, Any]] = []
    for (emp, month), units in sorted(grouped.items()):
        if len(units) > 1:
            anomalies.append(
                {
                    "type": "test_of_twos",
                    "employee_id": emp,
                    "month": month,
                    "unit_count": len(units),
                    "units": [
                        {
                            "worksite_id": u,
                            "wages": round(v["wages"], 2),
                            "hours": round(v["hours"], 2),
                            "periods": v["periods"],
                        }
                        for u, v in sorted(units.items())
                    ],
                    "resolution": "human_review",
                    "note": "Counted at multiple units this month — reviewer confirms which unit owns the headcount (no auto-drop).",
                }
            )
    return anomalies


def detect_scraggly_pay_periods(
    rows: list[dict[str, Any]],
    *,
    tax_year: int,
    state: str | None = None,
    min_wages: float = 50.0,
    min_hours: float = 4.0,
) -> list[dict[str, Any]]:
    """CALC-08 — low-value / trivial pay periods flagged for review.

    A period is "scraggly" when its gross wages are below `min_wages` AND its
    hours are below `min_hours` (e.g. $10 over a period, or a sub-weekly
    stray). Flagged, not removed — value is preserved; only the reviewer
    decides whether to drop the period *structure*.
    """
    scoped = _filter(rows, tax_year, state)
    anomalies: list[dict[str, Any]] = []
    for r, line_key in zip(scoped, pay_line_keys(scoped)):
        wages = float(r.get("Gross_Wages", 0.0) or 0.0)
        hours = float(r.get("Hours_Worked", 0.0) or 0.0)
        if wages < min_wages and hours < min_hours:
            anomalies.append(
                {
                    "type": "meaningful_pay_period",
                    "line_key": line_key,
                    "employee_id": str(r.get("Employee_ID", "")),
                    "worksite_id": str(r.get("Worksite_ID", "")),
                    "pay_period_start": r.get("Pay_Period_Start"),
                    "pay_period_end": r.get("Pay_Period_End"),
                    "pay_date": r.get("Pay_Date"),
                    "wages": round(wages, 2),
                    "hours": round(hours, 2),
                    "resolution": "human_review",
                    "note": "Trivial-value period — reviewer confirms before dropping structure (hours/wages retained).",
                }
            )
    return anomalies


def run_exception_report(
    rows: list[dict[str, Any]],
    *,
    tax_year: int,
    state: str | None = None,
    min_wages: float = 50.0,
    min_hours: float = 4.0,
) -> dict[str, Any]:
    """Combined exception report (AI-02) with a human-validation checkpoint.

    Returns both anomaly lists plus a summary. `clean` is True only when both
    lists are empty. `requires_human_validation` is always True when any
    anomaly exists — the agent surfaces, the human resolves.
    """
    twos = detect_test_of_twos(rows, tax_year=tax_year, state=state)
    scraggly = detect_scraggly_pay_periods(
        rows, tax_year=tax_year, state=state, min_wages=min_wages, min_hours=min_hours
    )
    total = len(twos) + len(scraggly)
    report = {
        "tax_year": tax_year,
        "state": state.upper() if state else None,
        "test_of_twos": twos,
        "meaningful_pay_period": scraggly,
        "summary": {
            "test_of_twos_count": len(twos),
            "meaningful_pay_period_count": len(scraggly),
            "total_anomalies": total,
            "clean": total == 0,
            "requires_human_validation": total > 0,
        },
        "thresholds": {"min_wages": min_wages, "min_hours": min_hours},
    }

    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step="Automated QC — test of twos + meaningful pay periods",
            inputs={"tax_year": tax_year, "state": state, "rows": len(_filter(rows, tax_year, state))},
            formula="group(employee,month) unit_count>1 (CALC-07); wages<min AND hours<min (CALC-08)",
            output=report["summary"],
            citation="Process § QC — test of twos + scraggly pay periods (human checkpoint)",
        )
    return report
